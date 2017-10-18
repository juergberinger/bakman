bakman
======
bakman is a Python-based backup tool using rsync and hard-links. Its primary purpose is to carry out semi-automatic backups using multiple external hard drives.

Features
--------
- Backups are based on rsync and hard-links following the ideas presented by Mike Rubel at <http://www.mikerubel.org/computers/rsync_snapshots/>.
- Supports multiple backup versions with automatic deletion of obsolete backups.
- Backups can include multiple partitions.
- Supports mounting of external hard drives, including LVM volumes and encrypted hard drives.
- Configuration of multiple backup profiles using configuration files written in Python.
- Modular design to make extension with user-specific backup actions easy.


Concepts
--------
Backups are defined in configuration files written in Python. Configuration files can contain multiple backup configurations. The desired configuration file is executed at run-time using ``execfile``.

Each backup configuration consists of multiple parts that can be run invidually or in any desired sequence. For example, a backup configuration might include a first part backing up the root partition, and a second part backing up /home.

Each part consists of one or more steps that typically might include actions to mount the backup destination, running the backup, and unmounting. Steps may be common to multiple parts, in which case they will be executed only once. For example, before any backup parts are run, an external hard drive receiving the backup may need to be mounted and decrypted using LUKS. After all backup parts have run, the drive will need to be properly unmounted.

Installation
------------
By default, backup configuration and log files are located in ``~/.bakman``. Alternatively you can set environment variable ``$UEADM`` to point to a directory with sub-directories ``etc`` and ``log`` for the configuration and log files, respectively.

Create a configuration file (default: ``bakman.conf.py``) and a file with exclude patterns (see rsync documentation, default: ``bakman.exclude``) in the configuration directory. ``bakman.py`` has options to use different configuration or exclude files.

Copy ``bakman.py`` to a directory in your PATH. Run ``bakman.py -h`` for instructions on how to run backups.

See ``sample.conf.py`` for a sample configuration file showing a few different backup configurations.
