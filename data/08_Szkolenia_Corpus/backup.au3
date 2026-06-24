; #NoTrayIcon
#include <File.au3>
#include <Array.au3>

; ============================================
; CONFIGURATION
; ============================================
Global Const $APP_TITLE        = "Corpus 6"
Global Const $WATCH_FOLDER     = "C:\Users\User\Documents\Corpus\"
Global Const $BACKUP_FOLDER    = "C:\Users\User\Documents\Corpus\Backups\"
Global Const $FILE_EXT         = "*.s3d"
Global Const $MAX_BACKUPS      = 10
Global Const $SAVE_INTERVAL    = 60000   ; Force save every 60 seconds
Global Const $CHECK_INTERVAL   = 2000    ; File watch every 2 seconds
Global Const $MIN_BACKUP_GAP   = 115000  ; 115s (gives 5s buffer for 2-minute interval)
Global Const $FILE_STABLE_WAIT = 1500    ; Wait for file to finish writing
Global Const $LOG_FILE         = @ScriptDir & "\corpus_backup.log"
Global Const $LOG_FILE_OLD     = @ScriptDir & "\corpus_backup.old.log"
Global Const $LOG_MAX_BYTES    = 1048576 ; 1MB max log size
Global Const $MIN_SIZE_CHANGE  = 200     ; Ignore file size changes smaller than 200 bytes
Global $g_iLastBackupSize      = 0       ; Tracks the size of the last successful backup

; ============================================
; STATE
; ============================================
Global $g_bOurSaveTriggered = False
Global $g_iLastBackupTime   = TimerInit()
Global $g_iAutoSaveTimer    = TimerInit()
Global $g_iFileWatchTimer   = TimerInit()
Global $g_sLastModified     = ""
Global $g_iBackupCount      = 0

; ============================================
; TRAY SETUP & AUTOIT OPTIONS
; ============================================
Opt("TrayMenuMode", 3)
Opt("TrayOnEventMode", 1)
Opt("WinTitleMatchMode", 2) ; CRITICAL FIX: Matches "Corpus 6" anywhere in the title (handles unsaved '*' asterisks)

TraySetIcon("shell32.dll", 258)
TraySetToolTip("Corpus6 Guard - Running")

Global $tSaveNow = TrayCreateItem("Save Now")
Global $tSep1    = TrayCreateItem("")
Global $tExit    = TrayCreateItem("Exit")

TrayItemSetOnEvent($tSaveNow, "ForceSave")
TrayItemSetOnEvent($tExit,    "ExitScript")
TraySetState(1)

; ============================================
; INIT
; ============================================
If Not FileExists($BACKUP_FOLDER) Then DirCreate($BACKUP_FOLDER)

WriteLog("INFO", "INIT", "=== Corpus6 Guard started ===")
WriteLog("INFO", "INIT", "AutoIt  : " & @AutoItVersion)
WriteLog("INFO", "INIT", "OS      : " & @OSVersion & " build " & @OSBuild)
WriteLog("INFO", "INIT", "Watching: " & $WATCH_FOLDER)
WriteLog("INFO", "INIT", "Backups : " & $BACKUP_FOLDER)

; Wait for things to settle before reading baseline
Sleep($CHECK_INTERVAL * 2)
$g_sLastModified = GetNewestFileTime()

WriteLog("INFO", "INIT", "Baseline file time: " & $g_sLastModified)
WriteLog("INFO", "INIT", "Ready - entering main loop")

TrayTip("Corpus6 Guard", "Protection active!", 2)

; ============================================
; MAIN LOOP
; ============================================
While True

    ; --- AUTOSAVE TICK ---
    If TimerDiff($g_iAutoSaveTimer) >= $SAVE_INTERVAL Then
        $g_iAutoSaveTimer = TimerInit()
        DoAutoSave()
    EndIf

    ; --- FILE WATCH TICK ---
    If TimerDiff($g_iFileWatchTimer) >= $CHECK_INTERVAL Then
        $g_iFileWatchTimer = TimerInit()
        CheckFileChange()
    EndIf

    Sleep(500)
WEnd


; ##############################################
; CORE FUNCTIONS
; ##############################################

; ============================================
; AUTO SAVE
; This is the PRIMARY purpose of this tool
; Force save Corpus 6 before it can crash
; ============================================
Func DoAutoSave()
    WriteLog("INFO", "AUTOSAVE", "Timer fired - checking app state")

    ; Is app running at all?
    If Not WinExists($APP_TITLE) Then
        WriteLog("WARN", "AUTOSAVE", "App not found - is Corpus 6 running?")
        Return
    EndIf

    ; Is app in focus?
    If Not WinActive($APP_TITLE) Then
        WriteLog("INFO", "AUTOSAVE", "App not in focus - skipping save")
        Return
    EndIf

    ; Activate and verify focus before sending keys
    WinActivate($APP_TITLE)
    Sleep(150)

    If Not WinActive($APP_TITLE) Then
        WriteLog("WARN", "AUTOSAVE", "Could not activate window - save aborted")
        Return
    EndIf

    ; Flag MUST be set before Send()
    ; Tells backup watcher this file change is ours
    $g_bOurSaveTriggered = True

    Send("^s")

    WriteLog("INFO", "AUTOSAVE", "Ctrl+S sent - file save triggered")
    TraySetToolTip("Corpus6 Guard | Saved: " & @HOUR & ":" & @MIN & ":" & @SEC)
EndFunc


; ============================================
; FORCE SAVE FROM TRAY
; ============================================
Func ForceSave()
    WriteLog("INFO", "AUTOSAVE", "Manual save from tray menu")
    DoAutoSave()
EndFunc


; ============================================
; CHECK FILE CHANGE
; Only backs up when WE triggered the save
; This is key to avoiding false positives
; ============================================
Func CheckFileChange()
    Local $sCurrentTime = GetNewestFileTime()

    ; No change - nothing to do
    If $sCurrentTime = $g_sLastModified Then Return

    ; File changed - update baseline immediately
    $g_sLastModified = $sCurrentTime
    WriteLog("INFO", "WATCHER", "File change detected at " & $sCurrentTime)

    ; GATE 1 - Was this OUR save?
    ; Blocks: app internal saves, antivirus,
    ;         blob noise, any external changes
    If Not $g_bOurSaveTriggered Then
        WriteLog("INFO", "GATE1", "Blocked - not our save - ignoring")
        Return
    EndIf
    $g_bOurSaveTriggered = False
    WriteLog("INFO", "GATE1", "Passed - confirmed our save")

    ; GATE 2 - Too soon since last backup?
    ; Blocks: rapid save storms
    Local $iElapsed = TimerDiff($g_iLastBackupTime)
    If $iElapsed < $MIN_BACKUP_GAP Then
        WriteLog("INFO", "GATE2", "Blocked - only " & Int($iElapsed/1000) & "s since last backup")
        Return
    EndIf
    WriteLog("INFO", "GATE2", "Passed - " & Int($iElapsed/1000) & "s since last backup")

    ; GATE 4 - Is the size change significant? (Ignores metadata/camera changes)
    Local $iCurrentSize = FileGetSize(GetNewestFilePath())
    If $g_iLastBackupSize > 0 And Abs($iCurrentSize - $g_iLastBackupSize) <= $MIN_SIZE_CHANGE Then
        WriteLog("INFO", "GATE4", "Blocked - minor size change (" & Abs($iCurrentSize - $g_iLastBackupSize) & " bytes). Skipping backup.")
        Return
    EndIf
    WriteLog("INFO", "GATE4", "Passed - significant size change detected")

    ; GATE 3 - Is file stable (finished writing)?
    ; Blocks: backing up half-written files
    If Not WaitForFileStable() Then
        WriteLog("WARN", "GATE3", "Blocked - file not stable - skipping backup")
        Return
    EndIf
    WriteLog("INFO", "GATE3", "Passed - file is stable")

    DoBackup()
EndFunc


; ============================================
; WAIT FOR FILE STABLE
; ============================================
Func WaitForFileStable()
    Local $sFile = GetNewestFilePath()
    If $sFile = "" Then Return False

    Local $iSize1 = FileGetSize($sFile)

    ; EDGE CASE FIX: Zero-Byte Crash Protection
    If $iSize1 = 0 Then
        WriteLog("ERROR", "STABLE", "File is 0 bytes! App likely crashed during save. Aborting.")
        Return False
    EndIf

    WriteLog("INFO", "STABLE", "Size before: " & $iSize1 & " bytes")
    Sleep($FILE_STABLE_WAIT)
    Local $iSize2 = FileGetSize($sFile)
    WriteLog("INFO", "STABLE", "Size after : " & $iSize2 & " bytes")

    If $iSize1 <> $iSize2 Then Return False

    ; EDGE CASE FIX: OS File Lock Check
    Local $hFile = FileOpen($sFile, 0) ; Try to open in read mode
    If $hFile = -1 Then
        WriteLog("WARN", "STABLE", "File size is stable, but file is locked by OS. Still writing?")
        Return False
    EndIf
    FileClose($hFile)

    Return True
EndFunc


; ============================================
; DO BACKUP
; ============================================
Func DoBackup()
    Local $sSourceFile = GetNewestFilePath()
    If $sSourceFile = "" Then Return

    Local $iSourceSize = FileGetSize($sSourceFile)
    Local $sBaseName   = StringReplace(GetNewestFileName(), ".s3d", "")
    Local $sTimestamp  = @YEAR & "-" & @MON  & "-" & @MDAY & "_" & @HOUR & "-" & @MIN & "-" & @SEC

    ; EDGE CASE FIX: Atomic Temp Copying
    Local $sFinalFile  = $BACKUP_FOLDER & $sBaseName & "_" & $sTimestamp & ".s3d"
    Local $sTempFile   = $sFinalFile & ".tmp"

    WriteLog("INFO", "BACKUP", "Source: " & $sSourceFile)

    ; 1. Copy to a temporary file first
    If Not FileCopy($sSourceFile, $sTempFile, 1) Then
        WriteLog("ERROR", "BACKUP", "FileCopy to .tmp FAILED.")
        Return
    EndIf

    ; 2. Verify the copy was 100% successful
    If FileGetSize($sTempFile) <> $iSourceSize Then
        WriteLog("ERROR", "BACKUP", "Size mismatch after copy! Disk full? Deleting temp file.")
        FileDelete($sTempFile)
        Return
    EndIf

    ; 3. Rename to final extension (Atomic operation)
    If Not FileMove($sTempFile, $sFinalFile, 1) Then
        WriteLog("ERROR", "BACKUP", "Failed to rename .tmp to .s3d")
        Return
    EndIf

        $g_iBackupCount   += 1
        $g_iLastBackupTime = TimerInit()
        $g_iLastBackupSize = $iSourceSize

    WriteLog("INFO", "BACKUP", "OK - backup #" & $g_iBackupCount & " | " & $iSourceSize & " bytes")
        TraySetToolTip("Corpus6 Guard | Backup #" & $g_iBackupCount & " at " & @HOUR & ":" & @MIN)
        TrayTip("Corpus6 Guard", "Backup #" & $g_iBackupCount & " saved!", 1)

        CleanOldBackups($sBaseName)
EndFunc


; ============================================
; CLEAN OLD BACKUPS - Keep last 10
; ============================================
Func CleanOldBackups($sBaseName)
    ; Safety Check: Prevent accidental mass deletion if basename is empty
    If StringStripWS($sBaseName, 8) = "" Then
        WriteLog("ERROR", "CLEANUP", "BaseName is empty! Aborting cleanup.")
        Return
    EndIf

    Local $aBackups = _FileListToArray($BACKUP_FOLDER, $sBaseName & "_*.s3d", 1)
    If @error Or $aBackups[0] = 0 Then Return

    If $aBackups[0] <= $MAX_BACKUPS Then Return

    ; Sort ascending (Oldest files at the top: index 1, 2, 3...)
    _ArraySort($aBackups, 0, 1)

    Local $iToDelete = $aBackups[0] - $MAX_BACKUPS
    WriteLog("INFO", "CLEANUP", "Removing " & $iToDelete & " oldest backup(s)")

    Local $iDeletedCount = 0

    For $i = 1 To $aBackups[0]
        If $iDeletedCount >= $iToDelete Then ExitLoop

        Local $sFilePath = $BACKUP_FOLDER & $aBackups[$i]

        ; EDGE CASE FIX 1: "Milestone" Protection (Never delete the absolute oldest backup)
        If $i = 1 Then
            WriteLog("INFO", "CLEANUP", "Preserving absolute oldest backup as Milestone: " & $aBackups[$i])
            $iToDelete += 1 ; We skipped one, so we need to delete one further down the list
            ContinueLoop
        EndIf

        ; EDGE CASE FIX 2: Shrinkage Protection (Don't delete good backups if newest is corrupted/tiny)
        Local $iThisSize = FileGetSize($sFilePath)
        Local $iNewestSize = FileGetSize($BACKUP_FOLDER & $aBackups[$aBackups[0]])

        If $iNewestSize < ($iThisSize * 0.5) Then
            WriteLog("WARN", "CLEANUP", "Newest backup is < 50% size of older backup! Halting cleanup to prevent data loss.")
            Return
        EndIf

        ; Safe to delete
        If FileDelete($sFilePath) Then
            WriteLog("INFO", "CLEANUP", "Deleted: " & $aBackups[$i])
            $iDeletedCount += 1
        Else
            WriteLog("WARN", "CLEANUP", "Could not delete: " & $aBackups[$i])
        EndIf
    Next
EndFunc


; ##############################################
; HELPERS
; ##############################################

Func GetNewestFileTime()
    Local $aFiles = _FileListToArray($WATCH_FOLDER, $FILE_EXT, 1)
    If @error Or $aFiles[0] = 0 Then Return ""

    Local $sNewest = ""
    For $i = 1 To $aFiles[0]
        Local $sTime = FileGetTime($WATCH_FOLDER & $aFiles[$i], 0, 1)
        If $sTime > $sNewest Then $sNewest = $sTime
    Next
    Return $sNewest
EndFunc

Func GetNewestFilePath()
    Local $aFiles = _FileListToArray($WATCH_FOLDER, $FILE_EXT, 1)
    If @error Or $aFiles[0] = 0 Then Return ""

    Local $sNewestFile = ""
    Local $sNewestTime = ""
    For $i = 1 To $aFiles[0]
        Local $sTime = FileGetTime($WATCH_FOLDER & $aFiles[$i], 0, 1)
        If $sTime > $sNewestTime Then
            $sNewestTime = $sTime
            $sNewestFile = $WATCH_FOLDER & $aFiles[$i]
        EndIf
    Next
    Return $sNewestFile
EndFunc

Func GetNewestFileName()
    Return StringTrimLeft(GetNewestFilePath(), StringLen($WATCH_FOLDER))
EndFunc


; ##############################################
; CYCLIC LOGGING SYSTEM
; ##############################################

; ============================================
; WRITE LOG
; Format: [2024-01-15 14:30:22] [INFO ] [AUTOSAVE  ] Message
; Cyclic: when log hits 1MB rename to .old.log
;         and start fresh - always max 2MB total
; ============================================
Func WriteLog($sLevel, $sModule, $sMessage)

    ; Check log size - rotate if over 1MB
    If FileExists($LOG_FILE) Then
        If FileGetSize($LOG_FILE) >= $LOG_MAX_BYTES Then
            RotateLog()
        EndIf
    EndIf

    ; Pad columns for readability
    Local $sLevelPad  = StringLeft($sLevel  & "     ", 5)
    Local $sModulePad = StringLeft($sModule & "          ", 10)
    Local $sTimestamp = @YEAR & "-" & @MON  & "-" & @MDAY & " " & @HOUR & ":" & @MIN  & ":" & @SEC

    Local $sLine = "[" & $sTimestamp & "] [" & $sLevelPad & "] [" & $sModulePad & "] " & $sMessage & @CRLF

    Local $hFile = FileOpen($LOG_FILE, 1)
    If $hFile <> -1 Then
        FileWrite($hFile, $sLine)
        FileClose($hFile)
    EndIf

    If $sLevel = "ERROR" Or $sLevel = "WARN" Then ConsoleWrite($sLine)
EndFunc


; ============================================
; ROTATE LOG
; Renames current log to .old.log
; Old .old.log is overwritten (max 2MB total)
; ============================================
Func RotateLog()
    ; Delete old rotation if exists
    If FileExists($LOG_FILE_OLD) Then FileDelete($LOG_FILE_OLD)

    ; Rename current to old
    FileMove($LOG_FILE, $LOG_FILE_OLD)

    ; Write rotation notice to new fresh log
    Local $hFile = FileOpen($LOG_FILE, 2)  ; 2 = create new / overwrite
    If $hFile <> -1 Then
        FileWrite($hFile, "[" & @YEAR & "-" & @MON & "-" & @MDAY & " " & @HOUR & ":" & @MIN & ":" & @SEC & "] " & _
                          "[INFO ] [LOG       ] === Log rotated - previous log saved to .old.log ===" & @CRLF)
        FileClose($hFile)
    EndIf
EndFunc


; ============================================
; EXIT HANDLER
; ============================================
Func ExitScript()
    WriteLog("INFO", "EXIT", "=== Corpus6 Guard stopped by user ===")
    WriteLog("INFO", "EXIT", "Total backups made this session: " & $g_iBackupCount)
    TrayTip("Corpus6 Guard", "Protection stopped.", 2)
    Sleep(1500)
    Exit
EndFunc