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
    
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,description=textwrap.dedent(parsehelp),epilog="For scrambling a file with a hexa key.")
    parser.add_argument('-p','--password', required = True, action=ArgValHex , help="password to be used")
    parser.add_argument('-f','--folder',  required=True, help="folder to work on")
    parser.add_argument('-x','--extension', required=False,  help="file extension")
    
    args = parser.parse_args()
    return args

def encode(file,password):
    if not password:
        print "no password set to encode/decode. "
        return
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
    fileo = os.path.join(filedir,'_'+_)
    if os.path.isfile(fileo):
        os.unlink(fileo)
    fo = open(fileo,'wb')
    f = open(file, "rb")
    try:
        byte = f.read(1)
        bd =ord(byte)
        bdx = bd ^ passwd1
        fo.write(chr(bdx))
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
            fo.write(chr(bdx))
    finally:
        f.close()
        fo.close()
    if os.path.isfile(file):
        os.unlink(file)
        os.rename(fileo, file)   
def scanfolder(args):    
    for root, dirs, files in os.walk(args.folder):
        for file in files:
            if args.extension:
                if file.endswith('.'+args.extension):
                    fl = os.path.join(root, file)
                    encode(fl,args.password)
            else:
                fl= os.path.join(root,file)
                encode(fl, args.password)
    #ecnode(fl , passwd)
if __name__ == "__main__":
    args = parsearguments()
    scanfolder( args)
