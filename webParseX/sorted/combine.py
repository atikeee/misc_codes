files = ['google.m3u8','hindi.m3u','pluto.m3u8','plex.m3u8','bangla.m3u','english.m3u','misc.m3u']
with open('combined.m3u','w') as fo:
    for file in files:
        print("FILE:"+file+"\n")
        with open(file,'r',encoding='utf-8') as f:
            for line in f:
                if(line.strip()!=""):
                    fo.write(line)
                    
        
