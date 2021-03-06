import Components.Task
from Components.config import config
from Components import Harddisk
from Components.GUIComponent import GUIComponent
from Components.VariableText import VariableText
import time
import os
import enigma

def getTrashFolder(path=None):
	# Returns trash folder without symlinks
	try:
		if path is None:
			print 'path is none'
		else:
			if path.find('/movie') >0:
				mountpoint = Harddisk.findMountPoint(os.path.realpath(path))
				trashcan = os.path.join(mountpoint, 'movie')
			else:
				trashcan = Harddisk.findMountPoint(os.path.realpath(path))
			return os.path.realpath(os.path.join(trashcan, ".Trash"))
	except:
		return ""

def createTrashFolder(path=None):
	trash = getTrashFolder(path)
	if not os.path.isdir(trash):
		os.mkdir(trash)
	return trash

def get_size(start_path = '.'):
	total_size = 0
	for dirpath, dirnames, filenames in os.walk(start_path):
		for f in filenames:
			fp = os.path.join(dirpath, f)
			total_size += os.path.getsize(fp)
	return total_size

class Trashcan:
	def __init__(self, session):
		self.session = session
		session.nav.record_event.append(self.gotRecordEvent)
		self.gotRecordEvent(None, None)

	def gotRecordEvent(self, service, event):
		self.recordings = len(self.session.nav.getRecordings())
		if (event == enigma.iRecordableService.evEnd):
			self.cleanIfIdle()

	def destroy(self):
		if self.session is not None:
			self.session.nav.record_event.remove(self.gotRecordEvent)
		self.session = None

	def __del__(self):
		self.destroy()

	def cleanIfIdle(self):
		# RecordTimer calls this when preparing a recording. That is a
		# nice moment to clean up.
		if self.recordings:
			print "[Trashcan] Recording in progress", self.recordings
			return
		ctimeLimit = time.time() - (config.usage.movielist_trashcan_days.value * 3600 * 24)
		reserveBytes = 1024*1024*1024 * int(config.usage.movielist_trashcan_reserve.value)
		clean(ctimeLimit, reserveBytes)

def clean(ctimeLimit, reserveBytes):
	isCleaning = False
	for job in Components.Task.job_manager.getPendingJobs():
		jobname = str(job.name)
		if jobname.startswith(_("Cleaning Trashes")):
			isCleaning = True
			break

	if config.usage.movielist_trashcan.value and not isCleaning:
		name = _("Cleaning Trashes")
		job = Components.Task.Job(name)
		task = CleanTrashTask(job, name)
		task.openFiles(ctimeLimit, reserveBytes)
		Components.Task.job_manager.AddJob(job)
	elif isCleaning:
		print "[Trashcan] Cleanup already running"
	else:
		print "[Trashcan] Disabled skipping check."

def cleanAll(path=None):
	trash = getTrashFolder(path)
	if not os.path.isdir(trash):
		print "[Trashcan] No trash.", trash
		return 0
	for root, dirs, files in os.walk(trash, topdown=False):
		for name in files:
			fn = os.path.join(root, name)
			try:
				enigma.eBackgroundFileEraser.getInstance().erase(fn)
			except Exception, e:
				print "[Trashcan] Failed to erase %s:"% name, e
		# Remove empty directories if possible
		for name in dirs:
			try:
				os.rmdir(os.path.join(root, name))
			except:
				pass

def init(session):
	global instance
	instance = Trashcan(session)

class CleanTrashTask(Components.Task.PythonTask):
	def openFiles(self, ctimeLimit, reserveBytes):
		self.ctimeLimit = ctimeLimit
		self.reserveBytes = reserveBytes

	def work(self):
		mounts=[]
		matches = []
		print "[Trashcan] probing folders"
		f = open('/proc/mounts', 'r')
		for line in f.readlines():
			parts = line.strip().split()
			mounts.append(parts[1])
		f.close()

 		for mount in mounts:
			if os.path.isdir(os.path.join(mount,'.Trash')):
				matches.append(os.path.join(mount,'.Trash'))
			if os.path.isdir(os.path.join(mount,'movie/.Trash')):
				matches.append(os.path.join(mount,'movie/.Trash'))

		print "[Trashcan] found following trashcan's:",matches
		if len(matches):
			for trashfolder in matches:
				print "[Trashcan] looking in trashcan",trashfolder
				trashsize = get_size(trashfolder)
				diskstat = os.statvfs(trashfolder)
				free = diskstat.f_bfree * diskstat.f_bsize
				bytesToRemove = self.reserveBytes - free
				print "[Trashcan] " + str(trashfolder) + ": Size:",trashsize
				candidates = []
				size = 0
				for root, dirs, files in os.walk(trashfolder, topdown=False):
					for name in files:
						try:
							fn = os.path.join(root, name)
							st = os.stat(fn)
							if st.st_ctime < self.ctimeLimit:
								enigma.eBackgroundFileEraser.getInstance().erase(fn)
								bytesToRemove -= st.st_size
							else:
								candidates.append((st.st_ctime, fn, st.st_size))
								size += st.st_size
						except Exception, e:
							print "[Trashcan] Failed to stat %s:"% name, e
					# Remove empty directories if possible
					for name in dirs:
						try:
							os.rmdir(os.path.join(root, name))
						except:
							pass
					candidates.sort()
					# Now we have a list of ctime, candidates, size. Sorted by ctime (=deletion time)
					for st_ctime, fn, st_size in candidates:
						if bytesToRemove < 0:
							break
						enigma.eBackgroundFileEraser.getInstance().erase(fn)
						bytesToRemove -= st_size
						size -= st_size
					print "[Trashcan] " + str(trashfolder) + ": Size now:",size

class TrashInfo(VariableText, GUIComponent):
	FREE = 0
	USED = 1
	SIZE = 2

	def __init__(self, path, type, update = True):
		GUIComponent.__init__(self)
		VariableText.__init__(self)
		self.type = type
		if update:
			self.update(path)

	def update(self, path):
		try:
			total_size = get_size(getTrashFolder(path))
		except OSError:
			return -1

		if self.type == self.USED:
			try:
				if total_size < 10000000:
					total_size = _("%d Kb") % (total_size >> 10)
				elif total_size < 10000000000:
					total_size = _("%d Mb") % (total_size >> 20)
				else:
					total_size = _("%d Gb") % (total_size >> 30)
				self.setText(_("Trashcan:") + " " + total_size)
			except:
				# occurs when f_blocks is 0 or a similar error
				self.setText("-?-")

	GUI_WIDGET = enigma.eLabel
