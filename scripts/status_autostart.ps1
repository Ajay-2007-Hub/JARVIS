$ErrorActionPreference = 'Stop'

# Query only the JARVIS task, without changing its state.
$Task = Get-ScheduledTask -TaskName 'JARVIS' -ErrorAction SilentlyContinue
if ($null -eq $Task) {
    Write-Output 'enabled=false'
    Write-Output 'last_run_result=not_registered'
    exit 0
}

# Include the last result code so startup failures can be diagnosed.
$Info = Get-ScheduledTaskInfo -TaskName 'JARVIS'
Write-Output 'enabled=true'
Write-Output ("last_run_result={0}" -f $Info.LastTaskResult)
