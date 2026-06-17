$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\Ciento Immobilier.lnk")
$Shortcut.TargetPath = "C:\Users\PC\Pictures\Ciento-Immobilier\start_ciento.bat"
$Shortcut.IconLocation = "C:\Users\PC\Pictures\Ciento-Immobilier\ciento_icon.ico"
$Shortcut.WorkingDirectory = "C:\Users\PC\Pictures\Ciento-Immobilier"
$Shortcut.WindowStyle = 7
$Shortcut.Save()
Write-Host "Raccourci créé sur le bureau avec succès."
