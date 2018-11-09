#!/usr/bin/env python
"""
bakman.py is a generic Linux backup tool. Backups are defined in a
Python-based configuration file as a set of parts that can be run
invidually or in any seqeuence. Each part consists of one or more
steps that typically include mount, running of a backup, and unmount
actions.

bakman.py can both run simple backups of one or several partitions
into a single pre-mounted location, or it can create a mirror image of
the disk being backed up onto a separate "clone" disk. It can mount
encrypted or unencrypted volumes and partitions on the fly as needed.
"""
__author__  = 'Juerg Beringer'
__version__ = '$Id: bakman.py 2241 2017-10-18 02:19:20Z jb $'
__usage__   = """%prog [options] cmd [cmdargs...]

Examples:

bakman list                 list configurations (* means config is available)
bakman list bakdisk5        list parts in configuration bakdisk5 (* means part is available)
bakman dump bakdisk5        show details of bakdisk5 backup configuration
bakman -v run bakdisk5      run bakdisk5 backup with progress updates
bakman -v -V run bakdisk5   dito but show also all files being transferred
bakman -v --debug --dryrun run bakdisk5
                            dito, but instead of executing commands show what would
                            be excecutedx
bakman -e jb --batch bakdisk5 winhome
                            run part winhome of bakdisk5 backup without confirmation
                            dialog, then e-mail log to local user jb
bakman -m /bakman mount clonedisk3
                            mount all parts in clonedisk3 configuration under /bakman/clonedisk3


Commands are:

list                   list defined backup configurations
list NAME              list parts in backup configuration NAME
dump NAME              dump backup configuration NAME
run NAME [part...]     run (including mount/unmount) all or selected part in configuration NAME
mount NAME [part...]   mount all or selected part in configuration NAME
unmount NAME [part...] unmount all or selected part in configuration NAME
debug                  enter interactive debug mode
"""

import os
import sys
import commands
import time
import logging
import cmdhelper
from cmdhelper import *


#
# Default configuration and log files
#
try:
    # If config and log files are kept under $UEADM
    UEADM = os.environ['UEADM']
    EXCLUDEPATTERN = '$UEADM/etc/bakman.exclude'
    LOGFILE = '$UEADM/log/bakman.log'
    CONFIGFILE = '$UEADM/etc/bakman.conf.py'
    DATEFILE = '$UEADM/log/bakman.dates'
except:
    # General case: .bakman in user's home dir
    UEADM = os.path.join(os.path.expanduser('~'),'.bakman')
    EXCLUDEPATTERN = os.path.join(UEADM,'bakman.exclude')
    LOGFILE = os.path.join(UEADM,'bakman.log')
    CONFIGFILE = os.path.join(UEADM,'bakman.conf.py')
    DATEFILE = os.path.join(UEADM,'bakman.dates')


#
# Generic utility functions
#
def checkSource(srcPath):
    """Return True if srcPath exists and is not empty."""
    if not os.path.exists(srcPath):
        return False
    return os.listdir(srcPath)!=[]

def checkDest(dstPath,isMountPoint=False):
    """Return True if dstPath exists and, if isMountPoint is True, is a mount point."""
    if not os.path.exists(dstPath):
        return False
    if isMountPoint and not os.path.ismount(dstPath):
        return False   # Only mount dir exists, but nothing is mounted there
    return True


#
# Classes for backup configuration and steps
#
class StepException(Exception):
    """Exception class that logs all exceptions occuring in steps."""

class Step:
    """Base class for all backup steps."""

    def __init__(self, keepAlive=False):
        self.keepAlive = keepAlive
        self.parentConfig = None
        self.mountPoint = None

    def setParentConfig(self,parentConfig):
        """Set parent BackupConfiguration instance."""
        self.parentConfig = parentConfig
        if self.mountPoint is None:
            self.mountPoint = self.mountPath()

    def __str__(self):
        """Return string with brief info about step."""
        return 'step base class'

    def device(self, devinfo=None):
        """Return path to device based on parent configuration."""
        return self.parentConfig.device(devinfo)

    def mountPath(self, relPath=None, path=None):
        """Determine path using parent configuration and given paths.

        If path is set, return path. Otherwise the mount point is
        determined from options.mountBase or the mountBase set in the
        parent BackupConfiguration, the name of the parent
        configuration, and relPath, if given."""
        if path is not None:
            return path
        mountBase = options.mountBase
        if mountBase is None:
            mountBase = self.parentConfig.mountBase
        if mountBase is None:
            mountBase = '/media'
        p = [ mountBase ]
        try:
            p.append(self.parentConfig.name)
        except:
            p.append('UNKNOWN')
            warning('mountPath called without parent configuration in step of class %s' % self.__class__.__name__)
        if relPath is not None:
            p.append(relPath)
        return os.path.sep.join(p)

    def isAvailable(self):
        """Return True if step can be done (virtual)."""
        return True

    def mount(self):
        """Mount or attach device (virtual)."""
        pass

    def run(self):
        """Carry out the backup (virtual)."""
        pass

    def unmount(self):
        """Unmount or detach device (virtual)."""
        pass


class Mount(Step):
    """Mount a partition."""

    def __init__(self, relPath, devinfo, mountOpts='', keepAlive=False, sleepBeforeUnmount=0):
        """Create mount step.

        If relPath is not empty, it will be appended to the default mount point.
        devinfo is either a device or a partition number for the disk
        defined in the parent configuration."""
        Step.__init__(self,keepAlive)
        self.relPath = relPath
        self.devinfo = devinfo
        self.mountOpts = '-o %s' % mountOpts if mountOpts else ''
        self.sleepBeforeUnmount = sleepBeforeUnmount

    def setParentConfig(self,parentConfig):
        Step.setParentConfig(self,parentConfig)
        if self.relPath:
            self.mountPoint = os.path.join(self.mountPoint,self.relPath)

    def __str__(self):
        device = self.device(self.devinfo)
        return 'Mount %s --> %s (options: %s)' % (device,self.mountPoint,self.mountOpts)

    def isAvailable(self):
        """Return true if device to be mounted is available.

        If the device path determined from self.devinfo and the parent configuration is
        not an absolute path, return True assuming that the device availability is being
        checked by a previous step."""
        device = self.device(self.devinfo)
        if device[:10] == '/dev/disk/':
            return os.path.exists(device)
        else:
            return True

    def mount(self):
        device = self.device(self.devinfo)
        #info('Mounting %s at %s' % (device,self.mountPoint))
        if not os.path.exists(self.mountPoint):
            run('mkdir -p %s' % self.mountPoint)
        run('mount %s %s %s' % (self.mountOpts,device,self.mountPoint), exceptionOnError=True)

    def unmount(self):
        device = self.device(self.devinfo)
        #info('Unmounting %s from %s' % (device,self.mountPoint))
        run('sync')
        if self.sleepBeforeUnmount:
            debug('waiting %i second(s) for device to settle' % self.sleepBeforeUnmount)
            time.sleep(self.sleepBeforeUnmount)
        run('umount %s' % self.mountPoint)


class LUKS(Step):
    """Attach a LUKS partition."""

    def __init__(self, name, devinfo, luksKey='', luksKeyFile='', keepAlive=False):
        """The device will be attached at /dev/mapper/bakman-name where name is the
           parameter name. The LUKS password is specified either directly in the configuration
           file as parameter luksKey, or indirectly in a file luksKeyFile."""
        Step.__init__(self,keepAlive)
        self.name = name
        self.devinfo = devinfo
        self.luksName = 'bakman-%s' % (name)   # Will be overridden by setParentConfig
        self.luksKey = luksKey
        self.luksKeyFile = luksKeyFile

    def __str__(self):
        device = self.device(self.devinfo)
        return 'LUKS volume %s --> %s' % (device,self.luksName)

    def setParentConfig(self,parentConfig):
        """Set parent BackupConfiguration instance."""
        Step.setParentConfig(self,parentConfig)
        self.luksName = '%s-%s' % (self.parentConfig.name,self.name)

    def isAvailable(self):
        device = self.device(self.devinfo)
        hasKey = self.luksKey or os.path.exists(self.luksKeyFile)
        return hasKey and os.path.exists(device)

    def mount(self):
        #info('Opening LUKS device %s' % (self.luksName))
        device = self.device(self.devinfo)
        if self.luksKeyFile:
            key = open(self.luksKeyFile,'r').read().strip()
        else:
            key = self.luksKey
        debug('running cmd: cryptsetup luksOpen %s %s > /dev/null 2>&1' % (device,self.luksName))
        cryptsetup = os.popen('cryptsetup luksOpen %s %s > /dev/null 2>&1' % (device,self.luksName), 'w')
        print >>cryptsetup, key
        cryptsetup.close()
        if not os.path.exists('/dev/mapper/'+self.luksName):
            raise StepException('Opening LUKS device %s failed' % self.luksName)

    def unmount(self):
        #info('Closing LUKS device %s' % (self.luksName))
        run('cryptsetup luksClose %s' % self.luksName)


class LVM(Step):
    """Attach a logical volume group."""

    def __init__(self, name, keepAlive=False):
        """Attach a logical volume group with the given name."""
        Step.__init__(self,keepAlive)
        self.name = name

    def __str__(self):
        return 'LVM volume %s' % self.name

    def mount(self):
        #info('Attaching logical volumes for group %s' % self.name)
        run('vgscan --mknodes' )
        run('vgchange -ay %s' % self.name, exceptionOnError=True)
        if not os.path.exists('/dev/'+self.name):
            raise StepException('Attaching logical volumes for group %s failed' % self.name)

    def unmount(self):
        #info('Detaching logical volumes for group %s' % (self.name))
        run('vgchange -an %s' % self.name)


class Command(Step):
    """Generic step class to execute a command."""

    def __init__(self, cmd, **kwargs):
        Step.__init__(self)
        self.cmd = cmd
        self.kwargs = kwargs

    def __str__(self):
        cmd = self.cmd % self.kwargs
        return 'Command: %s' % cmd

    def run(self):
        cmd = self.cmd % self.kwargs
        #info('    executing %s' % cmd)
        run(cmd, printOutput=options.verbose,dryrun=options.dryrun)


class SysBackup(Command):
    """Run sysbackup."""

    def __init__(self):
        Command.__init__(self, 'sysbackup')

    def __str__(self):
        return 'SysBackup (run cmd: %s)' % self.cmd


class CopyFiles(Step):
    """Copy files to target directory."""

    def __init__(self, targetDir, fileList=None):
        Step.__init__(self)
        self.fileList = fileList
        self.targetDir = targetDir

    def __str__(self):
        return 'CopyFiles (%s --> %s)' % (self.fileList,self.targetDir)

    def isAvailable(self):
        for f in self.fileList:
            if not os.path.exists(f):
                return False
        return os.path.exists(self.targetDir)

    def run(self):
        for f in self.fileList:
            run('/bin/cp -f --preserve=mode,timestamps %s %s' % (f,self.targetDir),
                dryrun=options.dryrun)
        run('/usr/bin/rm -f %s/LASTUPDATED-*.TIMESTAMP' % self.targetDir,
            dryrun=options.dryrun)
        run("/usr/bin/touch %s/`date '+LASTUPDATED-%%b-%%d-%%G.TIMESTAMP'`" % self.targetDir,
            dryrun=options.dryrun)


class RotateBackups(Step):
    """Rotate versioned backup files and delete superfluous copies."""

    def __init__(self, nKeep, dstDir, mountPoint=None):
        Step.__init__(self)
        self.nKeep = int(nKeep)
        self.dstDir = dstDir
        self.mountPoint = mountPoint
        self.path = None   # will be set by setParentConfig

    def setParentConfig(self,parentConfig):
        Step.setParentConfig(self,parentConfig)
        self.path = os.path.join(self.mountPoint,self.dstDir)

    def isAvailable(self):
        return os.path.exists(self.path)

    def __str__(self):
        return 'RotateBackups (keep %i old copies at %s)' % (self.nKeep,self.path)

    def run(self):
        if self.nKeep<=0:
            return
        delPath = os.path.join(self.path,str(self.nKeep))
        if delPath=='/' or ('*' in delPath) or ('%' in delPath) or ('?' in delPath):
            error('Found wildcard character in path %s - SKIPPING backup rotation' % delPath)
            return
        if os.path.exists(delPath):
            cmd = 'rm -rf %s' % delPath
            run(cmd, printOutput=True, dryrun=options.dryrun)
        for i in range(self.nKeep-1,-1,-1):
            srcPath = os.path.join(self.path,str(i))
            dstPath = os.path.join(self.path,str(i+1))
            if os.path.exists(srcPath):
                cmd = 'mv -f %s %s' % (srcPath,dstPath)
                run(cmd, printOutput=True, dryrun=options.dryrun)


class Rsync(Step):
    """Step class to run rsync."""

    def __init__(self, name, rsyncOpts='', rsyncArgs='-axHSAX --delete-excluded'):
        """Create rsync backup of single partition or directory.

           rsyncArgs are the default primary rsync arguments (-axHSAX
           --delete-excluded) and should normally not be changed by
           the user. Additional rsync options should be passed through
           parameter rsyncOpts. The command line options -n and -v
           will add the corresponding rsync options."""
        Step.__init__(self)
        self.name = name.replace('/','-')
        self.src = '/%s/' % name if not name=='root' else '/'
        self.rsyncOpts = rsyncOpts
        self.rsyncArgs = rsyncArgs

    def makeCommand(self):
        """Return string with full command line for rsync command."""
        opts = self.rsyncArgs
        if options.rsyncv:
            opts += ' -v'
        if options.rsyncn:
            opts += ' -n'
            if not options.rsyncv:
                opts += ' -v'
        if self.rsyncOpts:
            opts += ' '+self.rsyncOpts
        return 'rsync %s %s %s/%s' % (opts,self.src,self.mountPoint,self.name)

    def __str__(self):
        return 'Rsync: '+self.makeCommand()

    def isAvailable(self):
        return checkSource(self.src)

    def run(self):
        if checkSource(self.src):
            cmd = self.makeCommand()
            #info('    executing %s' % cmd)
            run(cmd, printOutput=True, dryrun=options.dryrun)
        else:
            warning('No files found in %s - skipping rsync' % src)


class RsArchive(Step):
    """rsarchive backup."""

    def __init__(self, dstDir, keepOldVersions, srcList, rsyncOpts='', rsyncArgs='-axHSAX --delete-excluded',
                 exclPatterns=EXCLUDEPATTERN, exclList=None,
                 mountPoint=None):
        """Create rsarchive backup using rsync.

        keepOldVersions can be set to False (single versions), True
        (multiple versions rotated externally) or to a positive
        integer n to automatically rotate through n version.
        --delete-excluded is automatically added to rsyncArgs if
        keepOldVersions is 0 or False."""
        Step.__init__(self)
        self.mountPoint = mountPoint
        self.path = None # will be set by setParentConfig
        self.dstDir = dstDir
        self.dstPath = None   # will be set by setParentConfig
        if isinstance(keepOldVersions,bool):
            # versioned, but rotating done outside of RsArchive
            self.isVersioned = keepOldVersions
            self.nKeep = 0
        else:
            self.isVersioned = (keepOldVersions>0)
            self.nKeep = int(keepOldVersions)
            if self.nKeep<0:
                self.nKeep=0
        self.srcList = srcList
        self.rsyncArgs = rsyncArgs
        self.rsyncOpts = rsyncOpts
        self.exclPatterns = exclPatterns
        self.exclList = exclList if exclList else []

    def setParentConfig(self,parentConfig):
        Step.setParentConfig(self,parentConfig)
        if self.dstDir:
            self.path = os.path.join(self.mountPoint,self.dstDir)
        else:
            self.path = self.mountPoint
        if self.isVersioned:
            self.linkPath = os.path.join(self.path,'1')
            self.dstPath = os.path.join(self.path,'0')
        else:
            self.dstPath = self.path

    def makeCommand(self, src):
        """Return string with full command line for rsync command."""
        cmd = ['rsync']
        cmd.append(self.rsyncArgs)
        if self.isVersioned:
            if src=='/':
                cmd.append(' --link-dest %s/root' % self.linkPath)
            else:
                cmd.append(' --link-dest %s' % self.linkPath)
        if self.rsyncOpts:
            cmd.append(self.rsyncOpts)
        if options.rsyncv:
            cmd.append('-v')
        if options.rsyncn:
            cmd.append('-n')
            if not options.rsyncv:
                cmd.append('-v')
        for e in self.exclList:
            cmd.append('--exclude=%s' % e)
        if self.exclPatterns:
            cmd.append('--exclude-from=%s' % self.exclPatterns)
        if src=='/':
            cmd.append('/  %s/root' % self.dstPath)
        else:
            cmd.append('%s  %s' % (src,self.dstPath))
        return ' '.join(cmd)

    def __str__(self):
        if self.nKeep>0:
            cmds = ['RsArchive (%s) - rotate to keep %i old copies' % (self.srcList,self.nKeep)]
        else:
            cmds = ['RsArchive (%s)' % self.srcList]
        for src in self.srcList:
            cmds.append('%1s %s' % ('*' if checkSource(src) else '',
                                   self.makeCommand(src)))
        return '\n'.join(cmds)

    def isAvailable(self):
        if not checkDest(self.mountPoint,True):
            return False
        for d in self.srcList:
            if not checkSource(d):
                return False
        return True

    def run(self):
        if not checkDest(self.mountPoint,True):
            error('Destination %s is not mounted' % self.mountPoint)
        else:
            if not os.path.exists(self.dstPath):
                run('mkdir -p %s' % self.dstPath, dryrun=options.dryrun)
            if self.nKeep>0:
                # rotate old versions
                info('%s starting rotate, keeping %s old versions ...' % (time.asctime(),self.nKeep))
                delPath = os.path.join(self.path,str(self.nKeep))
                if delPath=='/' or ('*' in delPath) or ('%' in delPath) or ('?' in delPath):
                    error('Found wildcard character in rotation path %s - skipping backup' % delPath)
                    return
                if os.path.exists(delPath):
                    cmd = 'rm -rf %s' % delPath
                    run(cmd, printOutput=True, dryrun=options.dryrun)
                for i in range(self.nKeep-1,-1,-1):
                    srcPath = os.path.join(self.path,str(i))
                    dstPath = os.path.join(self.path,str(i+1))
                    if os.path.exists(srcPath):
                        cmd = 'mv -f %s %s' % (srcPath,dstPath)
                        run(cmd, printOutput=True, dryrun=options.dryrun)
            for src in self.srcList:
                if checkSource(src):
                    info('%s starting rsync of %s ...' % (time.asctime(),src))
                    cmd = self.makeCommand(src)
                    run(cmd, printOutput=True, dryrun=options.dryrun)
                else:
                    warning('No files found in %s - skipping rsync' % src)
            stampPath = self.dstPath
            if (not self.dstDir) and len(self.srcList)==1 and self.srcList[0][-1]!='/':
                stampPath = os.path.join(stampPath,os.path.basename(self.srcList[0]))
            run('touch %s/RSARCHIVE.TIMESTAMP' % stampPath, dryrun=options.dryrun)


class BackupConfiguration:
    """Define a backup configuration."""

    def __init__(self, name, description, diskId=None, mountBase='/media', *commonSteps):
        self.name = name
        self.description = description
        self.diskId = diskId
        self.mountBase = mountBase
        self.commonSteps = commonSteps
        for s in commonSteps:
            s.setParentConfig(self)
        self.parts = []       # list of tuples (name,stepList)
        self.locked = False   # flag to prevent erroneous changes to configuration

    def lock(self):
        """Lock configuration."""
        self.locked = True

    def device(self,devinfo=None):
        """Return absolute device path to disk or partition.

        devinfo is either a device (/dev/...) or a partition number.
        In the former case, devinfo is returned. In the latter case,
        diskId and devinfo are used to obtain the full path to the
        partition's device. If devinfo is None, the path to the disk
        is returned, otherwise devinfo is assumed to be a partition
        number and the device path to that partition is returned."""
        if devinfo is None:
            return '/dev/disk/by-id/%s' % (self.diskId)
        try:
            if devinfo[0:5]=='/dev/':
                return devinfo
        except:
            pass
        return '/dev/disk/by-id/%s-part%i' % (self.diskId,devinfo)
        
    # FIXME: optional part argument to check if part is avaiable
    def isAvailable(self):
        """Return True if configuration is available."""
        if self.diskId is None:
            return True
        else:
            return os.path.exists(self.device())

    def isAvailableCommonSteps(self):
        """Return True if common steps are available."""
        for s in self.commonSteps:
            if not s.isAvailable():
                return False
        return True

    def definedParts(self):
        """Return list of all defined parts."""
        return [name for (name,steps) in self.parts]

    def availableParts(self):
        """Return list with names of available parts."""
        if not self.isAvailable():
            return []
        if not self.isAvailableCommonSteps():
            return []   # No parts available if common steps not available
        available = []
        for (name,steps) in self.parts:
            isAvailable = True
            for s in steps:
                isAvailable = isAvailable and s.isAvailable()
            if isAvailable:
                available.append(name)
        return available

    def add(self, name, *steps):
        """Add a new part with given steps."""
        if self.locked:
            raise RuntimeError('config file error: cannot add part %s to locked configuration %s' % (name,self.name))
        else:
            self.parts.append( (name,list(steps)) )
            for s in steps:
                s.setParentConfig(self)

    def steps(self, partName):
        """Return list of steps for part with name partName."""
        for (name,steps) in self.parts:
            if name==partName:
                return steps
        raise LookupError('Part %s not found' % partName)

    def uniqueStepConfiguration(self, partNames,
                                description='BackupConfiguration with unique steps for selected parts'):
        """Return a BackupConfiguration with unique steps for given parts."""
        steps = set()
        for s in self.commonSteps:
            steps.add(s)
        c = BackupConfiguration(self.name,description,self.diskId,self.mountBase,*self.commonSteps)
        for name in partNames:
            uniqueSteps = []
            c.parts.append( (name,uniqueSteps) )
            for s in self.steps(name):
                if not s in steps:
                    uniqueSteps.append(s)
                    steps.add(s)
        return c

    def dump(self):
        print 'Configuration %s (%s):' % (self.name,self.description)
        print '  --- steps marked as KEEP will be unmounted in reverse order at the end'
        print "  --- '*' denotes parts or actions that are available"
        print
        available = self.availableParts() if self.isAvailable() else []
        if len(self.parts)+len(self.commonSteps)>0:
            print '  %1s Common steps:' % ('*' if self.isAvailableCommonSteps() else '')
            def printStep(keepAlive,step):
                sep = '      KEEP  ' if keepAlive else  10*' '
                for l in str(step).split('\n'):
                    print sep,l
            for s in self.commonSteps:
                printStep(s.keepAlive,s)
            for (name,steps) in self.parts:
                print
                print '  %1s %s:' % ('*' if name in available else '',name)
                for s in steps:
                    printStep(s.keepAlive,s)
        else:
            print '\n%s has no parts' % self.name


#
# Utilities to manage configurations and execute commands
#
def prepareConfig(cmdargs):
    """Return (configName,config,partList).

    configName is the name of the configuration.
    config is a copy of configuration configName that has only unique steps.
    partList is the list of available parts to use."""
    configName = cmdargs[0]
    try:
        config = configDict[configName]
    except:
        raise LookupError('Configuration %s not found' % configName)
    availableParts = config.availableParts()
    definedParts = config.definedParts()
    excludeParts = options.excludeParts.split(',')
    parts = []
    tryParts = cmdargs[1:] if len(cmdargs)>1 else config.definedParts()
    for p in tryParts:
        if p in availableParts:
            if not p in excludeParts:
                parts.append(p)
        else:
            if len(cmdargs)>1:
                error('Part %s of configuration %s is not available or not defined.' % (p,configName))
            else:
                warning('Part %s not available - skipping' % p)
    info('')
    info('Configuration:    %s' % configName)
    info('Defined parts:    %s' % definedParts)
    info('Available parts:  %s' % availableParts)
    info('Excluded parts:   %s' % excludeParts)
    info('Using parts:      %s' % parts)
    return (configName,config.uniqueStepConfiguration(parts),parts)

def execute(partList, config, doMount=False, doRun=False, doUnmount=False):
    """Execute a actions on steps in selected parts."""
    fmt = 'starting  %-8s  for step  %-16s    (%s)'

    # Check that bakman is not running already
    # FIXME - see e.g. http://stackoverflow.com/questions/788411/check-to-see-if-python-script-is-running

    # Check if there are any steps. This takes also care of preventing execution
    # of unavailable common steps (if common steps are not available, no parts are
    # available.
    if len(partList)==0:
        return

    # Check that we are root
    if os.geteuid()!=0:
        error('Must run as root')
        sys.exit(1)

    # Common steps
    info('')
    info('%s Processing common steps ...' % (time.asctime()))
    if doMount:
        for s in config.commonSteps:
            debug(fmt % ('mount',s.__class__.__name__,'common steps'))
            s.mount()
    if doRun:
        for s in config.commonSteps:
            debug(fmt % ('run',s.__class__.__name__,'common steps'))
            s.run()
    if doUnmount:
        for s in reversed(config.commonSteps):
            if not s.keepAlive:
                debug(fmt % ('unmount',s.__class__.__name__,'common steps'))
                s.unmount()

    # Process parts
    for p in partList:
        info('')
        info('%s Processing part %s ...' % (time.asctime(),p))
        steps = config.steps(p)
        if doMount:
            for s in steps:
                debug(fmt % ('mount',s.__class__.__name__,p))
                s.mount()
        if doRun:
            for s in steps:
                debug(fmt % ('run',s.__class__.__name__,p))
                s.run()
        if doUnmount:
            for s in reversed(steps):
                if not s.keepAlive:
                    debug(fmt % ('unmount',s.__class__.__name__,p))
                    s.unmount()

    # Finalize parts kept alive and common steps
    if doUnmount:
        for p in reversed(partList):
            for s in reversed(config.steps(p)):
                if s.keepAlive:
                    debug(fmt % ('finalize',s.__class__.__name__,p))
                    s.unmount()
        for s in reversed(config.commonSteps):
            if s.keepAlive:
                debug(fmt % ('finalize',s.__class__.__name__,'common steps'))
                s.unmount()

    # Done
    info('')
    info('%s Done' % (time.asctime()))


#
# Command line execution
#
if __name__ == '__main__':
    cmdHelper = CmdHelper('optparse', __version__, __usage__,
                   hasInteractive=True,
                   hasBatch=True,
                   logFile=LOGFILE,
                   logSeparator=70*'-',
                   logTimestampFmt='%(asctime)s %(levelname)-8s ')
    defaultConfigFile = CONFIGFILE
    defaultRunLogFile = DATEFILE
    cmdHelper.add_option('', '--runlog', dest='runlog', default=os.path.expandvars(defaultRunLogFile),
                         help='path to run log file (default: %s)' % defaultRunLogFile)
    cmdHelper.add_option('-c', '--config', dest='config', default=os.path.expandvars(defaultConfigFile),
                         help='path to config file (default: %s)' % defaultConfigFile)
    cmdHelper.add_option('-m', '--mount', dest='mountBase', default=None,
                         help='base mount point for backup partitions mounted by bakman (default: /media)')
    cmdHelper.add_option('-x', '--exclude', dest='excludeParts', default='',
                         help='comma-separated string of parts to exclude')
    cmdHelper.add_option('', '--modify-window', dest='modifywindow', type=int, default='3601',
                         help='rsync: set maximum time differencee to ignore (used only for FAT '
                         'filesystems, default: 3601)')
    cmdHelper.add_option('-V', '--rsyncv', dest='rsyncv', action='store_true', default=False,
                         help='rsync: show files being transferred')
    cmdHelper.add_option('-n', '--rsyncn', dest='rsyncn', action='store_true', default=False,
                         help='rsync: only show what would be done but do not copy anything')
    cmdHelper.add_option('', '--dryrun', dest='dryrun', action='store_true', default=False,
                         help='only log commands (use --debug), but do not execute anything in run step '
                         '(mount/unmount are still executed)')
    (options,args) = cmdHelper.parse()
    if len(args) < 1:
        error('wrong number of command line arguments')
        sys.exit(1)

    # Command processing
    cmd = args[0]
    cmdargs = args[1:]
    cmdOk = False
    try:

        # Read config file
        configDict = {}
        execfile(options.config,globals(),configDict)

        # List defined configuration
        if cmd=='list' and len(cmdargs)==0:
            print 'Configuration:   %s' % options.config
            print 'Log file:        %s' % options.logfile
            print
            print 'List of backup configurations (* means configration is available):'
            for configName in sorted(configDict.keys()):
                if not isinstance(configDict[configName],BackupConfiguration):
                    continue
                config = configDict[configName]
                print '  %1s  %-15s   %s' % ('*' if config.isAvailable() else '',
                                             config.name,
                                             config.description)
            cmdOk = True

        # List parts in configuration
        if cmd=='list' and len(cmdargs)==1:
            configName = cmdargs[0]
            try:
                config = configDict[configName]
            except:
                raise LookupError('Configuration %s not found' % configName)
            available = config.availableParts() if config.isAvailable() else []
            print 'Parts in configuration %s (* means part is available):' % configName
            for (name,steps) in config.parts:
                print '  %1s  %-15s' % ('*' if name in available else ' ',name)
            cmdOk = True

        # Dump configuration
        if cmd=='dump' and len(cmdargs)==1:
            configName = cmdargs[0]
            try:
                config = configDict[configName]
            except:
                raise LookupError('Configuration %s not found' % configName)
            config.dump()
            cmdOk = True

        # Mount all or selected parts in specific configuration
        if cmd=='mount' and (len(cmdargs)==1 or len(cmdargs)==2):
            (configName,stepConfig,parts) = prepareConfig(cmdargs)
            execute(parts,stepConfig,doMount=True)
            cmdOk = True

        # Unmount all or selected parts in specific configuration
        if cmd=='unmount' and (len(cmdargs)==1 or len(cmdargs)==2):
            (configName,stepConfig,parts) = prepareConfig(cmdargs)
            execute(parts,stepConfig,doUnmount=True)
            cmdOk = True

        # Run all or selected parts in specific configuration
        if cmd=='run' and len(cmdargs)>=1:
            (configName,stepConfig,parts) = prepareConfig(cmdargs)
            if not options.batch:
                if not parts:
                    error('Nothing to run - backup aborted.')
                    sys.exit(1)
                try:
                    config = configDict[configName]
                except:
                    raise LookupError('Configuration %s not found' % configName)
                print
                config.dump()
                print
                confirm('Execute backup with parts %s' % parts)
            execute(parts,stepConfig,doMount=True,doRun=True,doUnmount=True)
            if not options.dryrun:
                with open(options.runlog,'a') as f:
                    line = time.strftime('%a %b %d %X %Z %Y '+cmdLine(True)+'\n')
                    f.write(line)
            cmdOk = True

        # Enter interactive debug mode
        if cmd=='debug':
            os.environ['PYTHONINSPECT'] = '1'
            print 'Entering interactive mode (configDict contains configuration info) ...'
            cmdOk = True

        if not cmdOk:
            raise CmdError('illegal command or number of arguments')

    except Exception, e:
        handleError(e,options.debug)
    except KeyboardInterrupt:
        error('Backup aborted by user (CTRL-C)')
        sys.exit(1)
