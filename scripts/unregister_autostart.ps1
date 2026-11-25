$ErrorActionPreference = 'Stop'

# Remove only the named JARVIS task; leaving an absent task is already the desired state.
$Task = Get-ScheduledTask -TaskName 'JARVIS' -ErrorAction SilentlyContinue
if ($null -ne $Task) {
    Unregister-ScheduledTask -TaskName 'JARVIS' -Confirm:$false
    Write-Output 'Unregistered scheduled task JARVIS.'
} else {
    Write-Output 'Scheduled task JARVIS is not registered.'
}
