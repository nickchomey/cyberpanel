import json
import os.path
import sys
import argparse
import django
import requests
sys.path.append('/usr/local/CyberCP')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "CyberCP.settings")
django.setup()
from firewall.models import FirewallRules
from plogical.firewallUtilities import FirewallUtilities
from plogical.processUtilities import ProcessUtilities
from plogical.CyberCPLogFileWriter import CyberCPLogFileWriter as logging

class ClusterManager:

    LogURL = "http://de-a.cyberhosting.org:8000/HighAvailability/RecvData"
    ClusterFile = '/home/cyberpanel/cluster'
    vhostConfPath = '/usr/local/lsws/conf/vhosts'

    def __init__(self, type):
        ##
        ipFile = "/etc/cyberpanel/machineIP"
        f = open(ipFile)
        ipData = f.read()
        self.ipAddress = ipData.split('\n', 1)[0]
        ##
        self.config = json.loads(open(ClusterManager.ClusterFile, 'r').read())
        self.type = type

    def PostStatus(self, message):
        try:
            finalData = {'name': self.config['name'], 'type': self.type, 'message': message, 'token': self.config['token']}
            resp = requests.post(ClusterManager.LogURL, data=json.dumps(finalData), verify=False)
            logging.writeToFile(resp.text + '[info]')
        except BaseException as msg:
            logging.writeToFile('%s. [31:404]' % (str(msg)))

    def FetchMySQLConfigFile(self):

        if ProcessUtilities.decideDistro() == ProcessUtilities.centos:
            return '/etc/mysql/conf.d/cluster.cnf'
        else:
            return '/etc/mysql/conf.d/cluster.cnf'

    def DetechFromCluster(self):
        try:

            command = 'rm -rf %s' % (self.FetchMySQLConfigFile())
            ProcessUtilities.normalExecutioner(command)

            command = 'systemctl stop mysql'
            #ProcessUtilities.normalExecutioner(command)

            command = 'systemctl restart mysql'
            #ProcessUtilities.executioner(command)

            self.PostStatus('Successfully detached. [200]')

        except BaseException as msg:
            self.PostStatus('Failed to detach, error %s [404].' % (str(msg)))

    def SetupCluster(self):
        try:

            CentOSPath = '/etc/redhat-release'

            if os.path.exists(CentOSPath):
                cronPath = '/var/spool/cron/root'
            else:
                cronPath = '/var/spool/cron/crontabs/root'

            ClusterPath = self.FetchMySQLConfigFile()
            ClusterConfigPath = '/home/cyberpanel/cluster'
            config = json.loads(open(ClusterConfigPath, 'r').read())

            if self.type == 'Child':

                writeToFile = open(ClusterPath, 'w')
                writeToFile.write(config['ClusterConfigFailover'])
                writeToFile.close()

                writeToFile = open(cronPath, 'a')
                writeToFile.write('*/5 * * * * /usr/local/CyberCP/bin/python /usr/local/CyberCP/plogical/ClusterManager.py --function CreatePendingVirtualHosts --type Child\n')
                writeToFile.close()

            else:
                writeToFile = open(ClusterPath, 'w')
                writeToFile.write(config['ClusterConfigMaster'])
                writeToFile.close()

                writeToFile = open(cronPath, 'a')
                writeToFile.write('*/%s * * * * /usr/local/CyberCP/bin/python /usr/local/CyberCP/plogical/ClusterManager.py --function SyncNow --type Master\n' % (str(self.config['syncTime'])))
                writeToFile.write('*/3 * * * * /usr/local/CyberCP/bin/python /usr/local/CyberCP/plogical/ClusterManager.py --function PingNow --type Master\n')
                writeToFile.close()

            command = 'systemctl restart cron'
            ProcessUtilities.normalExecutioner(command)

            try:
                ### MySQL Public

                newFireWallRule = FirewallRules(name="mysqlpub", port='3306', proto="tcp")
                newFireWallRule.save()
                FirewallUtilities.addRule('tcp', '3306', "0.0.0.0/0")

                ### For Galera Cluster replication traffic.

                newFireWallRule = FirewallRules(name="galery", port='4567', proto="tcp")
                newFireWallRule.save()
                FirewallUtilities.addRule('tcp', '4567', "0.0.0.0/0")

                ### For Galera Cluster IST

                newFireWallRule = FirewallRules(name="galeryist", port='4568', proto="tcp")
                newFireWallRule.save()
                FirewallUtilities.addRule('tcp', '4568', "0.0.0.0/0")

                ### For Galera Cluster SST

                newFireWallRule = FirewallRules(name="galerysst", port='4444', proto="tcp")
                newFireWallRule.save()
                FirewallUtilities.addRule('tcp', '4444', "0.0.0.0/0")

                ### For Galera Cluster replication traffic. (UDP)

                newFireWallRule = FirewallRules(name="galeryudp", port='4567', proto="udp")
                newFireWallRule.save()
                FirewallUtilities.addRule('udp', '4567', "0.0.0.0/0")

            except:
                self.PostStatus('Failed to add Firewall rules, manually open the required ports..')


            self.PostStatus('Successfully attached to cluster. [200]')

            ###

        except BaseException as msg:
            self.PostStatus('Failed to attach, error %s [404].' % (str(msg)))

    def BootMaster(self):
        try:

            command = 'systemctl stop mysql'
            ProcessUtilities.normalExecutioner(command)

            command = 'galera_new_cluster'
            ProcessUtilities.normalExecutioner(command)

            self.PostStatus('Master server successfully booted. [200]')

            ###

        except BaseException as msg:
            self.PostStatus('Failed to boot, error %s [404].' % (str(msg)))

    def BootChild(self):
        try:

            ChildData = '/home/cyberpanel/childaata'
            data = json.loads(open(ChildData, 'r').read())

            ## CyberPanel DB Creds

            ## Update settings file using the data fetched from master


            dbName = data['dbName']
            dbUser = data['dbUser']
            password = data['password']
            host = data['host']
            port = data['port']

            ## Root DB Creds

            rootdbName = data['rootdbName']
            rootdbdbUser = data['rootdbdbUser']
            rootdbpassword = data['rootdbpassword']

            completDBString = """\nDATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': '%s',
        'USER': '%s',
        'PASSWORD': '%s',
        'HOST': '%s',
        'PORT':'%s'
    },
    'rootdb': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': '%s',
        'USER': '%s',
        'PASSWORD': '%s',
        'HOST': '%s',
        'PORT': '%s',
    },
}\n""" % (dbName, dbUser, password, host, port, rootdbName, rootdbdbUser, rootdbpassword, host, port)

            settingsFile = '/usr/local/CyberCP/CyberCP/settings.py'

            settingsData = open(settingsFile, 'r').readlines()

            DATABASESCHECK = 0
            writeToFile = open(settingsFile, 'w')

            for items in settingsData:
                if items.find('DATABASES = {') > -1:
                    DATABASESCHECK = 1

                if DATABASESCHECK == 0:
                    writeToFile.write(items)

                if items.find('DATABASE_ROUTERS = [') > -1:
                    DATABASESCHECK = 0
                    writeToFile.write(completDBString)
                    writeToFile.write(items)

            writeToFile.close()

            ## new settings file restored

            command = 'systemctl stop mysql'
            ProcessUtilities.normalExecutioner(command)

            command = 'systemctl start mysql'
            ProcessUtilities.normalExecutioner(command)

            ## Restart lscpd

            command = 'systemctl restart lscpd'
            ProcessUtilities.normalExecutioner(command)

            ## Update root password in cyberpanel file

            writeToFile = open('/etc/cyberpanel/mysqlPassword', 'w')
            writeToFile.write(rootdbpassword)
            writeToFile.close()

            ## Update root password in .my.cnf

            writeToFile = open('/home/cyberpanel/.my.cnf', 'w')
            content = """[mysqldump]
user=root
password=%s
max_allowed_packet=1024M
[mysql]
user=root
password=%s""" % (rootdbpassword, rootdbpassword)

            writeToFile.write(content)
            writeToFile.close()

            self.PostStatus('Fail over server successfully booted. [200]')

            ###

        except BaseException as msg:
            self.PostStatus('Failed to boot, error %s [404].' % (str(msg)))

    def CreatePendingVirtualHosts(self):
        try:

            from plogical.virtualHostUtilities import virtualHostUtilities
            from websiteFunctions.models import Websites, ChildDomains

            for website in Websites.objects.all():

                confPath = '%s/%s' % (ClusterManager.vhostConfPath, website.domain)
                if not os.path.exists(confPath):
                    self.PostStatus('Domain %s found in master server, creating on child server now..' % (website.domain))
                    virtualHostUtilities.createVirtualHost(website.domain, website.adminEmail, website.phpSelection, website.externalApp, 1, 1, 0, website.admin.userName, website.package.packageName, 0, '/home/cyberpanel/temp', 1, 0)
                    self.PostStatus('Domain %s successfully created.' % (website.domain))


            for childDomain in ChildDomains.objects.all():
                confPath = '%s/%s' % (ClusterManager.vhostConfPath, childDomain.domain)
                if not os.path.exists(confPath):
                    self.PostStatus('Child Domain %s found in master server, creating on child server now..' % (childDomain.domain))
                    virtualHostUtilities.createDomain(childDomain.master.domain, childDomain.domain, childDomain.phpSelection, childDomain.path, 1, 1, 0, childDomain.master.admin.userName, 0, 0)
                    self.PostStatus('Child Domain %s successfully created.' % (childDomain.domain))

            ## Cleanup of deleted domains

            from plogical.acl import ACLManager
            import validators
            currentACL = ACLManager.loadedACL(1)
            allSite = ACLManager.findAllSites(currentACL, 1)

            for website in os.listdir(ClusterManager.vhostConfPath):

                if website not in allSite:
                    self.PostStatus(
                        'Domain %s not found in Master, deleting data directories and configurations.' % (website))

                    command = 'rm -rf /home/%s' % (website)
                    ProcessUtilities.normalExecutioner(command)

                    command = 'rm -rf /%s/%s' % (ClusterManager.vhostConfPath, website)
                    ProcessUtilities.normalExecutioner(command)



            self.PostStatus('All domains synced.')

        except BaseException as msg:
            self.PostStatus('Failed to create pending vhosts, error %s [404].' % (str(msg)))

    def SyncNow(self):
        try:
            self.PostStatus('Syncing data from home directory to fail over server..')

            command = "rsync -avzp -e 'ssh -o StrictHostKeyChecking=no -p %s -i /root/.ssh/cyberpanel' /home root@%s:/" % (self.config['failoverServerSSHPort'], self.config['failoverServerIP'])
            ProcessUtilities.normalExecutioner(command)

            self.PostStatus('Syncing SSL certificates to fail over server..')

            command = "rsync -avzp -e 'ssh -o StrictHostKeyChecking=no -p %s -i /root/.ssh/cyberpanel' /etc/letsencrypt root@%s:/etc" % (
            self.config['failoverServerSSHPort'], self.config['failoverServerIP'])
            ProcessUtilities.normalExecutioner(command)

            self.PostStatus('Data and SSL certificates currently synced.')

        except BaseException as msg:
            self.PostStatus('Failed to create pending vhosts, error %s [404].' % (str(msg)))

    def PingNow(self):
        try:
            self.PostStatus('Master up. [200]')
        except BaseException as msg:
            self.PostStatus('Failed to ping cloud for online status, error %s [404].' % (str(msg)))


def main():
    parser = argparse.ArgumentParser(description='CyberPanel Installer')
    parser.add_argument('--function', help='Function to run.')
    parser.add_argument('--type', help='Type of detach.')

    args = parser.parse_args()

    uc = ClusterManager(args.type)

    if args.function == 'DetachCluster':
        uc.DetechFromCluster()
    elif args.function == 'SetupCluster':
        uc.SetupCluster()
    elif args.function == 'BootMaster':
        uc.BootMaster()
    elif args.function == 'BootChild':
        uc.BootChild()
    elif args.function == 'CreatePendingVirtualHosts':
        uc.CreatePendingVirtualHosts()
    elif args.function == 'SyncNow':
        uc.SyncNow()
    elif args.function == 'PingNow':
        uc.PingNow()


if __name__ == "__main__":
    main()