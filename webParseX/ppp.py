
#import requests
import urllib.request 
from urllib.request import urlopen, Request
import urllib.error
from lxml import html
import re,sys
#import requests
import urllib.request 
beg = 1
end = 0 
n = len(sys.argv)
if n>2:
    bs = sys.argv[1]
    es = sys.argv[2]
else:
    print("pass 2 number argument for lines to process")
    exit()
beg = int(bs)
end = int(es)
f = open("_input.txt", "r",encoding="utf-8")
src = ""
dst = "zzz.m3u"
n = 0 
with open(dst, 'w',encoding="utf-8") as file_o:
    file_o.write(r'')

for line in f:
    n = n+1
    if end>0 and (n>end):
        break
    if (n<beg):
        continue
    if not line.startswith('#'):
        
        if(line.strip()==""):
            continue
        

        if( line.startswith("https://www.pornhub")):
            print("\nPornHub "+str(n)+": "+str(line))
            try:
                data = urllib.request.urlopen(line)
                tree = html.fromstring(data.read()) 
                item = tree.xpath(r'//*[@id="player"]/script[1]/text()')
                title = str(n)+"." + tree.xpath(r'//h1/span')[0].text+"|pornhub"
            except urllib.error.HTTPError as e:
                print(e)
                continue
            except Exception as e2:
                print ("Error",e2)
                continue
            #/html/body/div[5]/div[2]/div[3]/div[1]/div[1]/div[1]/div[1]/script[1]/text()
            #//*[@id="player"]/script[1]/text()
            #//*[@id="hd-leftColVideoPage"]/div[1]/div[4]/h1/span
            #title = tree.xpath(r'//*[@id="videoTitle"]/span')[0].text
            if(len(item)>0):
                res = item[0]
                #print(res)
                p = r'"videoUrl":"(.*?)"'
                #p = r'"mediaDefinitions":\[(.*?)\]'
                links = re.findall(p,res)
                if(len(links)>0):
                    #link = links[0]
                    highres=0
                    l = ""
                    
                    for link in reversed(links):
                        #print(link+"\n")
                        #m = re.match(r'.*?\D(\d+)P_\d+K.*',link)
                        m = re.match(r'.*?\D(\d+)P_\d+K.*',link)
                        #print("$$"+link)
                        #m = re.match(r'.*?(?<=\/)(\d+)P_\d+K.*',link)
                        if m:
                            #print(m.group(1))
                            newres = int(m.group(1))
                            if newres>highres:
                                highres = newres
                                l = link.replace('\\','')
                                with open(dst, 'a',encoding="utf-8") as file_o:
                                    file_o.write(r'#EXTINF:-1 group-title="ph",'+title+"\n")
                                    file_o.write(l+"\n")
                                
                                #with open("input_ph_bkp.txt", 'a',encoding="utf-8") as file_o:
                                #   file_o.write(line)
                                
                    print("final: "+l)
        elif(line.startswith("https://pornheal.com")):
            print("\nFreshPorno " + str(n) + ": " + str(line))
            headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'}
            try:
                req = Request(url=line.strip(), headers=headers)
                h = urlopen(req).read()
                tree = html.fromstring(h)
                # Find the video tag and its src attribute
                # This XPath might need adjustment based on the actual page structure
                #print(tree.text_content())
                video_src = tree.xpath('//video[@class="fp-engine"]/@src')
                print(video_src)
                title_elements = tree.xpath('//title/text()') # Get page title or specific video title
                print(title_elements)

                if video_src and len(video_src) > 0:
                    video_link = video_src[0]
                    title = str(n) + "." + (title_elements[0] if title_elements else "FreshPorno Video")
                    print("link: " + video_link + "\n")
                    with open(dst, 'a', encoding="utf-8") as file_o:
                        file_o.write(r'#EXTINF:-1 group-title="fp",'+title+"\n")
                        file_o.write(video_link+"\n")
                else:
                    print("Could not find video src on FreshPorno page.")

            except Exception as e:
                print("Error processing FreshPorno link:", e)
        
        
        elif(line.startswith("https://xhamster")):
            print("\nXHamster "+str(n)+": "+str(line))
            headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'}
            #reg_url = r'https://xhamster.com/videos/cory-chase-xh4wieL'
            #reg_url = r'https://xhamster.com/videos/oh-yeah-stepdaddy-fuck-me-while-no-one-sees-xhyhNvv'
            reg_url = line
            try:
                req = Request(url=reg_url,headers=headers)
                h = urlopen(req).read()
                tree = html.fromstring(h) 
                items = tree.xpath(r'/html/head/link')
                title = str(n) +"."+ tree.xpath(r'//title')[0].text
                for i in items:
                    
                    l= i.attrib['href']
                    if l.endswith("m3u8"):
                        print("link: "+l+"\n")
                        with open(dst, 'a') as file_o:
                            file_o.write(r'#EXTINF:-1 #EXTINF:-1  group-title="xh",'+title+"\n")
                            file_o.write(l+"\n")                       
            except Exception as e:
                print (e)
        
f.close()
#f = open("input_ph.txt", "w")
#f.close()
