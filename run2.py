import paramiko
import sys
import os
import time
import getopt


class SSHParamiko(object):
 
    err = "argument passwd or rsafile can not be None"
 
    def __init__(self, host, port, user, passwd=None, rsafile=None):
        self.h = host
        self.p = port
        self.u = user
        self.w = passwd
        self.rsa = rsafile
 
    def _connect(self):
        if self.w:
            return self.pwd_connect()
        elif self.rsa:
            return self.rsa_connect()
        else:
            raise ConnectionError(self.err)
 
    def _transfer(self):
        if self.w:
            return self.pwd_transfer()
        elif self.rsa:
            return self.rsa_transfer()
        else:
            raise ConnectionError(self.err)
 
    def pwd_connect(self):
        conn = paramiko.SSHClient()
        conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        conn.connect(self.h, self.p, self.u, self.w)
        return conn
 
    def rsa_connect(self):
        pkey = paramiko.RSAKey.from_private_key_file(self.rsa)
        conn = paramiko.SSHClient()
        conn.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        conn.connect(hostname=self.h, port=self.p, username=self.u, pkey=pkey)
        return conn
 
    def pwd_transfer(self):
        transport = paramiko.Transport(self.h, self.p)
        transport.connect(username=self.u, password=self.w)
        sftp = paramiko.SFTPClient.from_transport(transport)
        return sftp, transport
 
    def rsa_transfer(self):
        pkey = paramiko.RSAKey.from_private_key_file(self.rsa)
        transport = paramiko.Transport(self.h, self.p)
        transport.connect(username=self.u, pkey=pkey)
        sftp = paramiko.SFTPClient.from_transport(transport)
        return sftp, transport
 
    def run_cmd(self, cmd):
        conn = self._connect()
        if(cmd.strip().startswith("nohup")):
            conn.exec_command(cmd)
            return '1'
        stdin, stdout, stderr = conn.exec_command(cmd)
        code = stdout.channel.recv_exit_status()
        stdout, stderr = stdout.read(), stderr.read()
        conn.close()
        if not stderr:
            return code, stdout.decode()
        else:
            return code, stderr.decode()
 
    def get_file(self, remote, local):
        sftp, conn = self._transfer()
        sftp.get(remote, local)
        conn.close()
 
    def put_file(self, local, remote):
        sftp, conn = self._transfer()
        sftp.put(local, remote)
        conn.close()
        
        
    def exe_cmd_and_stout_always2(self, cmd, timeOut):
        conn = self._connect()
        res = []
        if timeOut:
            cmd = "timeout %s  %s" % (timeOut,cmd)
        sin,sout,serr = conn.exec_command(cmd)
        def line_buffered(f):
            line_buf = ""
            while not f.channel.exit_status_ready():
                try:
                    line_buf += f.read(1).decode()
                except Exception as e :
                    line_buf =''
                    print(e)
                if line_buf.endswith('\n'):
                    yield line_buf
                    line_buf = ''

        for l in line_buffered(sout):
            res.append(l)
            print(l.strip())
        conn.close()
        return res

def readYaml(p='配置文件yaml'):
    import yaml
    """
    pip install pyyaml
    http://ansible-tran.readthedocs.io/en/latest/docs/YAMLSyntax.html
    """
    with open(p, encoding='utf-8') as f:
        res = yaml.load(f, Loader=yaml.FullLoader)
        #print(res)
    return res;

def testConnection(h, p, u, dep_path,w=None, rsafile=None):
    try:
        print("--------连接服务器:"+h)
        if w:
            obj = SSHParamiko(h, p, u, passwd = w)
        else :
            obj = SSHParamiko(h, p, u, rsafile = rsafile)
        # r = obj.run_cmd("df -h")
        # print(r[0])
        # print(r[1])
        
        r = obj.run_cmd("date")
        print("服务器时间 :"+r[1])
        checkAndMkdir(dep_path,obj)
        
    except Exception as e :
        print(e)
        obj =None
    return obj

# 单个文件
def uploadFils(f,obj,remotePath):
    print("---上传文件: "+remotePath)
    s= obj.put_file(f,remotePath)


def checkAndMkdir(remotePath ,obj):
    #print("---检测路径: "+remotePath)
    cmd = """
    if [ ! -d "%s" ];then
    echo "---创建文件夹"
    mkdir -p %s
    else
    echo "---文件夹存在"
    fi
    """ % (remotePath,remotePath)
    r = obj.run_cmd(cmd)
    #print(r[1])


def runCommds(deployAfter,obj):
    a = deployAfter['cmdsWaiteTime'] if deployAfter and deployAfter.__contains__("cmdsWaiteTime") else 2
    if deployAfter and deployAfter.__contains__("cmds"):
        for i in deployAfter['cmds']:
            print("--- run cmd : %s"% i)
            r = obj.run_cmd(i)
            for j in r:
                print(j)
            if(len(deployAfter['cmds'])>1):
                print("--- 等待%s  秒,保证命令执行完成 "% a)
                time.sleep(a)
    if deployAfter and deployAfter.__contains__("logs"):
        logs = deployAfter['logs']
        if logs and logs.__contains__("cmd") \
            and logs.__contains__("showTimes"):
            obj.exe_cmd_and_stout_always2(logs['cmd'],logs['showTimes'])


# 总文件夹
def iteers(path,obj,func):
    if not os.path.isdir(path): 
        uploadFils(path,obj,func(path))
        return 
    files= os.listdir(path)
    for file in files: #遍历文件夹
        if not os.path.isdir(path+"/"+file):
            try:
                uploadFils(path+"/"+file,obj,func(path+"/"+file))
            except Exception as e:
                print(e)
                return False
        else :
            if os.path.isdir(path+"/"+file):
                checkAndMkdir(func(path+"/"+file),obj)
                iteers(path+"/"+file,obj,func)
            else:
                print("这是什么鬼玩意")

def main(argv):
    cfg = None
    fpath = None
    try:
        opts, args = getopt.getopt(argv,"hc:f:",["help","cfg=","file="])
    except getopt.GetoptError:
        print ('参数错误 -c <配置文件yaml> -f <上传文件>')
        sys.exit(2)
    for opt, arg in opts:
        if opt in ("-h","--help"):
            print ('参数 -c <配置文件yaml> -f <files>')
            sys.exit()
        elif opt in ("-c", "--cfg"):
            cfg = arg
        elif opt in ("-f", "--file"):
            fpath = arg
            
            
    if(cfg):
        if fpath and os.path.exists(fpath):
            fpath=os.path.abspath(fpath)
        # 读取配置文件
        if cfg and os.path.exists(cfg):
            taskCfgList = readYaml(os.path.abspath(cfg));
        else:
            taskCfgList = readYaml();
        # 获取上传文件信息
        for i in taskCfgList:
            dep_path = i['deployPath']
            
            if i.__contains__('rsaFile'):
                obj = testConnection(i['ip'],i['port'],i['username'],dep_path,rsafile = i['rsaFile'])
            elif i.__contains__('passwd'):
                obj =  testConnection(i['ip'],i['port'],i['username'],dep_path,w = i['passwd'])
            else:
                print("密码啊啊啊 ")
            if obj:
                try :
                    if not fpath:
                        print("-------> 没有上传文件")
                    print("""-------> 当前服务器为 : %s   \n
                        是否进行部署?
                        1. y 是的
                        2. n 跳到下一个
                        3. exit 退出程序
                    """ % (i['ip']))
                    a = input("请输入:")
                    if("y" == a or "yes" ==a ):
                        if fpath :
                            def transPath(localTransPath):
                                localProjectPath =  fpath
                                projectName = os.path.basename(localProjectPath) 
                                remotBasePath = dep_path
                                if not os.path.isdir(localProjectPath):
                                    return remotBasePath+"/"+projectName
                                return remotBasePath+"/"+projectName+"/"+localTransPath.replace(localProjectPath,"")
                            #上传文件
                            iteers(fpath,obj,transPath)
                        else:
                            pass
                        #之后的任务
                        if(i.__contains__('deployAfter')):
                            runCommds(i['deployAfter'],obj)
                        print("-------> 服务器: %s 部署完成" % (i['ip']))
                    elif("exit" == a):
                        sys.exit(1)
                    else:
                        pass
                except Exception as e:
                    print(e)
    else:
         print ('参数 -c <配置文件yaml> -f <上传的文件>')
        
        
if __name__ == '__main__':
    main(sys.argv[1:])