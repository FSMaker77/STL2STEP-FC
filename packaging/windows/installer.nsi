; STL2STEP FC - Windows x86_64 installer (per-user, no admin required).
; Built from Linux with makensis; the payload is a bundled CPython runtime.

Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

!ifndef VERSION
  !define VERSION "0.2.1"
!endif
!ifndef PAYLOAD
  !error "PAYLOAD is not defined"
!endif
!ifndef EXTRAS
  !error "EXTRAS is not defined"
!endif
!ifndef OUTFILE
  !error "OUTFILE is not defined"
!endif

Name "STL2STEP FC"
BrandingText "STL2STEP FC ${VERSION}"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\STL2STEP"
InstallDirRegKey HKCU "Software\STL2STEP" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 128

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "STL2STEP FC"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "FileDescription" "STL2STEP FC installer"
VIAddVersionKey /LANG=1033 "CompanyName" "STL2STEP contributors"
VIAddVersionKey /LANG=1033 "LegalCopyright" "MIT License"

!define MUI_ICON "stl2step.ico"
!define MUI_UNICON "stl2step.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\STL2STEP.exe"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "STL2STEP FC richiede Windows a 64 bit."
    Abort
  ${EndIf}
  SetShellVarContext current
FunctionEnd

Function un.onInit
  SetShellVarContext current
FunctionEnd

Section "STL2STEP FC (obbligatorio)" SecCore
  SectionIn RO
  SetOutPath "$INSTDIR"

  !cd "${PAYLOAD}"
  File /r "*.*"

  !cd "${EXTRAS}"
  File "LICENSE"
  File "README.md"

  SetOutPath "$INSTDIR\samples"
  File "samples/*.stl"
  SetOutPath "$INSTDIR"
SectionEnd

Section "Scorciatoia sul desktop" SecDesktop
  CreateShortcut "$DESKTOP\STL2STEP FC.lnk" "$INSTDIR\STL2STEP.exe" "" "$INSTDIR\STL2STEP.exe" 0
SectionEnd

Section "Menu Start" SecStartMenu
  CreateDirectory "$SMPROGRAMS\STL2STEP FC"
  CreateShortcut "$SMPROGRAMS\STL2STEP FC\STL2STEP FC.lnk" "$INSTDIR\STL2STEP.exe" "" "$INSTDIR\STL2STEP.exe" 0
  CreateShortcut "$SMPROGRAMS\STL2STEP FC\Disinstalla STL2STEP FC.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

Section -Post
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKCU "Software\STL2STEP" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\STL2STEP" "Version" "${VERSION}"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "DisplayName" "STL2STEP FC"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "DisplayIcon" "$INSTDIR\STL2STEP.exe,0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "Publisher" "STL2STEP contributors"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "NoRepair" 1

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP" "EstimatedSize" "$0"

  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\STL2STEP.exe" "" "$INSTDIR\STL2STEP.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\STL2STEP.exe" "Path" "$INSTDIR"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir /r "$INSTDIR"

  Delete "$DESKTOP\STL2STEP FC.lnk"
  RMDir /r "$SMPROGRAMS\STL2STEP FC"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\STL2STEP"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\App Paths\STL2STEP.exe"
  DeleteRegKey HKCU "Software\STL2STEP"
SectionEnd
