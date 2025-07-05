^+q:: {
    activeTitle := WinGetTitle("A")
    
    if InStr(activeTitle, " - Google Chrome") || InStr(activeTitle, " - Mozilla Firefox") || InStr(activeTitle, " - Microsoft Edge") {
        Send("^l") ; Focus address bar
        Sleep(100)
        Send("^c") ; Copy URL
        Sleep(100)
        ClipWait(1)
        url := A_Clipboard
        filePath := "C:\Users\PV_SupQS_SKU3-1\Documents\URL_Log.txt" ; Change this path
        FileAppend(url "`n", filePath)
        TrayTip("URL Saved", url, 2)
    } 
}
