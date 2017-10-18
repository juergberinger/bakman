# Sample bakman.py configuration files
#
# WARNING: this file will be executed by execfile when bakman.py is run
#


#
# Simple single-version backup of /home to an external hard drive mounted by the user prior to the backup
#
simpleBackup = BackupConfiguration('simpleBackup','simple backup example',
                                   'usb-some-disk-id')
simpleBackup.add('home', Rsync('home'))
simpleBackup.lock()


#
# Simple multi-version backup of /home to an external hard drive mounted by the user prior to the backup
#
multiVersionBackup = BackupConfiguration('multiVersionBackup','simple backup example',
                                   'usb-some-disk-id')
multiVersionBackup.add('home', RsArchive('home', 5, ['/home/']))
multiVersionBackup.lock()


#
# Backup of / and /home onto a LUKS-encrypted hard drive that will be automatically mounted
# at /backup. 3 previous backup versions will be kept. In addition, a single version of /var
# is backed up.
#
encryptedBackup = BackupConfiguration('encryptedBackup','backup to encrypted LVM volume',
                                      'usb-some-disk-id',
                                      '/backup',
                                      LUKS('main',1,'sample LUKS key password',keepAlive=True),
                                      Mount('','/dev/mapper/encryptedBackup-main',keepAlive=True))
encryptedBackup.add('example', RsArchive('example', 3, ['/','/home/']))
encryptedBackup.add('var',     RsArchive('var', False, ['/var/']))
encryptedBackup.lock()
