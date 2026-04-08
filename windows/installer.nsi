; LocalDrop NSIS Installer Script
; Produces: LocalDrop-Setup.exe
; Requirements: NSIS 3.x  (https://nsis.sourceforge.io)
; Build from repo root: makensis windows/installer.nsi
;
; Expects PyInstaller to have already produced:
;   dist/LocalDrop.exe  (one-file build)

Unicode True

;-------------------------------------------------
; General
;-------------------------------------------------
!define APP_NAME        "LocalDrop"
!define APP_VERSION     "1.0.0"
!define APP_PUBLISHER   "LocalDrop"
!define APP_URL         "https://github.com/YOUR_USERNAME/localdrop"
!define APP_EXE         "LocalDrop.exe"
!define INSTALL_DIR     "$PROGRAMFILES64\${APP_NAME}"
!define UNINST_KEY      "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define STARTMENU_DIR   "$SMPROGRAMS\${APP_NAME}"

Name            "${APP_NAME} ${APP_VERSION}"
OutFile         "LocalDrop-Setup.exe"
InstallDir      "${INSTALL_DIR}"
InstallDirRegKey HKLM "${UNINST_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor    /SOLID lzma
BrandingText     "${APP_NAME} ${APP_VERSION} Installer"

;-------------------------------------------------
; Interface
;-------------------------------------------------
!include "MUI2.nsh"

!define MUI_ABORTWARNING
!define MUI_ICON   "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"

; Installer pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

;-------------------------------------------------
; Installer sections
;-------------------------------------------------
Section "MainSection" SEC01
    SetOutPath "$INSTDIR"

    ; Copy the bundled executable
    File "..\dist\${APP_EXE}"
    ; Copy icon for shortcuts
    File "..\assets\icon.ico"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; --- Start Menu shortcuts ---
    CreateDirectory "${STARTMENU_DIR}"
    CreateShortcut  "${STARTMENU_DIR}\${APP_NAME}.lnk" \
                    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico" 0
    CreateShortcut  "${STARTMENU_DIR}\Uninstall ${APP_NAME}.lnk" \
                    "$INSTDIR\Uninstall.exe"

    ; --- Desktop shortcut ---
    CreateShortcut  "$DESKTOP\${APP_NAME}.lnk" \
                    "$INSTDIR\${APP_EXE}" "" "$INSTDIR\icon.ico" 0

    ; --- Add/Remove Programs registry entry ---
    WriteRegStr   HKLM "${UNINST_KEY}" "DisplayName"      "${APP_NAME}"
    WriteRegStr   HKLM "${UNINST_KEY}" "DisplayVersion"   "${APP_VERSION}"
    WriteRegStr   HKLM "${UNINST_KEY}" "Publisher"        "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${UNINST_KEY}" "URLInfoAbout"     "${APP_URL}"
    WriteRegStr   HKLM "${UNINST_KEY}" "InstallLocation"  "$INSTDIR"
    WriteRegStr   HKLM "${UNINST_KEY}" "UninstallString"  "$INSTDIR\Uninstall.exe"
    WriteRegStr   HKLM "${UNINST_KEY}" "DisplayIcon"      "$INSTDIR\icon.ico"
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoModify"         1
    WriteRegDWORD HKLM "${UNINST_KEY}" "NoRepair"         1

    ; Estimate size (bytes → KB)
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${UNINST_KEY}" "EstimatedSize" "$0"

    ; --- Windows Firewall: allow inbound on default port ---
    nsExec::ExecToLog 'netsh advfirewall firewall add rule name="LocalDrop" \
        protocol=TCP dir=in localport=5005 action=allow profile=private'

SectionEnd

;-------------------------------------------------
; Uninstaller section
;-------------------------------------------------
Section "Uninstall"
    ; Remove firewall rule
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="LocalDrop"'

    ; Delete installed files
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\icon.ico"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"

    ; Remove shortcuts
    Delete "${STARTMENU_DIR}\${APP_NAME}.lnk"
    Delete "${STARTMENU_DIR}\Uninstall ${APP_NAME}.lnk"
    RMDir  "${STARTMENU_DIR}"
    Delete "$DESKTOP\${APP_NAME}.lnk"

    ; Remove registry entry
    DeleteRegKey HKLM "${UNINST_KEY}"
SectionEnd
