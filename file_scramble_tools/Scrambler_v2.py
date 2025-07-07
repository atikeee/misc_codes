import sys,os,ConfigParser,argparse,textwrap,re

class ArgValHex(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        m = re.match(r'^[0-9a-f]{8}$',values,re.I)
        if m:
        #if values != "bar":
            #print "Got value:", values
            #raise ValueError("Not a bar!")
            setattr(namespace, self.dest, values)
        else:
            print "please add exactly 8 Hex digit for the password"


def parsearguments():
    parsehelp ="""
    This Program can be used to delete and clear env variables. 
    ============================================================

    """
    
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,description=textwrap.dedent(parsehelp),epilog="For scrambling a file with a key.")
    parser.add_argument('-p','--password', required = False, action=ArgValHex , help="password to be used.",default = 'abcd1234')
    parser.add_argument('-f','--folder',  required=True, help="folder to work on")
    parser.add_argument('-x','--extension', required=False,  help="file extension")
    xparser = parser.add_mutually_exclusive_group(required = True)
    xparser.add_argument('-c','--combined', required=False, action = 'store_true' , help="combine all input files")
    xparser.add_argument('-s','--split', required=False, action = 'store_true' , help="split files to multiple")
    xparser.add_argument('-d','--delete', required=False, action = 'store_true' , help="make the inputdelete")
    xparser.add_argument('-k','--keep', required=False, action = 'store_true' , help="scramble in current location")
    parser.add_argument('-n','--name', required=False, help="Combined file name.")
    args = parser.parse_args()
    return args
class scramblefile:
    def __init__(self,args):
        self.fo = None
        self.splitprocess = False
        self.args = args
        filename ='combined.z'
        records = 'combined.r'
        
        if args.name:
            filename = args.name+'.z'
            records = args.name + '.r'
        self.filerecord = os.path.join(self.args.folder,records)
        self.fileo = os.path.join(self.args.folder,filename)
        if self.args.combined:
            self.filerecordh = open(self.filerecord,'wb')
            if os.path.isfile(self.fileo):
                os.unlink(self.fileo)
            self.fo = open(self.fileo,'ab')
        elif self.args.split:
            if os.path.isfile(self.filerecord) and os.path.isfile(self.fileo):
                self.splitprocess = True
        self.filesprocessed = []
            
    def close(self):
        if self.args.combined:
            self.filerecordh.close()
            self.fo.close()
    def decode(self):
        if not self.splitprocess:
            print 'Input file is not found'
            return 
        password = self.args.password
        password1 = password[0:2]
        password2 = password[2:4]
        password3 = password[4:6]
        password4 = password[6:8]
        passwd1 = int('0x'+password1, 16)
        passwd2 = int('0x'+password2, 16)
        passwd3 = int('0x'+password3, 16)
        passwd4 = int('0x'+password4, 16)
        allinfo = []
        filerecordh = open(self.filerecord,'rb')
        wholefile = filerecordh.read()
        lines = wholefile.split('\n')
        for line in lines:
            info =  line.split('\t')
            if len(info)>1:
                oneset = [info[0], int(info[1])]
                allinfo.append(oneset)
        print allinfo
        allinfoindx = 0 
        filerecordh.close()
        filesz = allinfo[allinfoindx]
        curfile = os.path.join( self.args.folder,filesz[0][1:])
        curfolder = os.path.dirname(curfile)
        if not os.path.isdir(curfolder):
            os.makedirs(curfolder)
        cursz = allinfo[allinfoindx][1]
        #print curfile,self.args.folder
        
        try:
            self.fo = open(curfile,'wb')
            f = open(self.fileo, "rb")
            byte = f.read(1)
            if len(byte)>0:
                bd =ord(byte)
                bdx = bd ^ passwd1
                self.fo.write(chr(bdx))
            i = 0
            while byte != "":
                i +=1
                #print type(i),i,type(cursz),cursz,i>cursz
                if i == cursz:
                    #print 'match',allinfoindx
                    i=0
                    allinfoindx+=1
                    if(len(allinfo)>allinfoindx):
                        self.fo.close()
                        filesz = allinfo[allinfoindx]
                        curfile = os.path.join( self.args.folder,filesz[0][1:])
                        curfolder = os.path.dirname(curfile)
                        if not os.path.isdir(curfolder):
                            os.makedirs(curfolder)
                        cursz = allinfo[allinfoindx][1]
                        self.fo=open(curfile,'wb')
                    
                    
                j=i%4
                if j == 1:
                    passwd = passwd2
                elif j ==2:
                    passwd = passwd3
                elif j== 3:
                    passwd = passwd4
                elif j==0:
                    passwd = passwd1
                byte = f.read(1)
                #print 's',byte,type(byte),len(byte)
                if(len(byte)):
                    bd =ord(byte)
                    bdx = bd ^ passwd
                
                self.fo.write(chr(bdx))

        finally:
            self.fo.close()
            f.close()
    def encode(self,file):
        password = self.args.password
        if not password:
            print "no password set to encode/decode. "
            return
        curfile = file.replace(self.args.folder,'')
        password1 = password[0:2]
        password2 = password[2:4]
        password3 = password[4:6]
        password4 = password[6:8]
        print "Now processing file: "+file
        passwd1 = int('0x'+password1, 16)
        passwd2 = int('0x'+password2, 16)
        passwd3 = int('0x'+password3, 16)
        passwd4 = int('0x'+password4, 16)
        filedir,_ = os.path.split(file)
        self.fileo = os.path.join(filedir,'_'+_)
        
            
        if not self.args.combined:
            self.fo = open(self.fileo ,'wb')
        #    if os.path.isfile(fileo):
        #        os.unlink(fileo)
        #fo = open(fileo,'wb')
        f = open(file, "rb")
        
        try:
            byte = f.read(1)
            if len(byte)>0:
                bd =ord(byte)
                bdx = bd ^ passwd1
                self.fo.write(chr(bdx))
            i = 0
            while byte != "":
                i +=1
                j=i%4
                if j == 1:
                    passwd = passwd2
                elif j ==2:
                    passwd = passwd3
                elif j== 3:
                    passwd = passwd4
                elif j==0:
                    passwd = passwd1
                byte = f.read(1)
                #print 's',byte,type(byte),len(byte)
                if(len(byte)):
                    bd =ord(byte)
                    bdx = bd ^ passwd
                    self.fo.write(chr(bdx))
            if self.args.combined:
                self.filerecordh.write("{0}\t{1}\n".format(curfile,i))
                print curfile,i
        finally:
            f.close()
        if not self.args.combined:
            self.fo.close()
            if os.path.isfile(file):
                os.unlink(file)
                os.rename(self.fileo, file)
    def functiondist(self):
        if self.args.split:

            self.decode()

        elif self.args.combined or self.args.keep:
            self.scanandscramble()
        elif self.args.delete:
            self.deletefiles()
    def scanandscramble(self):
        if self.args.password:        
            for root, dirs, files in os.walk(self.args.folder):
                for file in files:
                    if self.args.extension:
                        if file.lower().endswith('.'+self.args.extension.lower()):
                            fl = os.path.join(root, file)
                            self.encode(fl)
                            
                    else:
                        if file.endswith('.z') or file.endswith('.r'):
                            print 'skip output file'
                        else:
                            fl= os.path.join(root,file)
                            self.encode(fl)
                            
    def deletefiles(self):
        filesprocessed = []
        if os.path.isfile(self.filerecord):
            filerecordh = open(self.filerecord,'rb')
            wholefile = filerecordh.read()
            lines = wholefile.split('\n')
            for line in lines:
                info =  line.split('\t')
                if len(info)>1:
                    filesprocessed.append(info[0])
            for f in filesprocessed:
                curfile = os.path.join( self.args.folder,f[1:])
                if os.path.isfile(curfile):
                    print 'deleting file', curfile
                    os.unlink(curfile)
                else:
                    print 'file not found as expected.',curfile
        else:
            print 'Record file not found '+self.args.name+'.r'
            #ecnode(fl , passwd)
if __name__ == "__main__":
    args = parsearguments()
    #print args
    sf = scramblefile(args)
    sf.functiondist()
    
    sf.close()
