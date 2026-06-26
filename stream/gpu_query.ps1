# VRAM total via Win32_VideoController
$vramObj = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Select-Object -First 1
if ($vramObj) {
    $vramGB = [math]::Round($vramObj.AdapterRAM / 1GB, 1)
    Write-Output "VRAM=$vramGB"
} else {
    Write-Output "VRAM=0"
}

# GPU utilization via Get-Counter
$engines = Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -ErrorAction SilentlyContinue
if ($engines -and $engines.CounterSamples) {
    $avg = ($engines.CounterSamples | Measure-Object CookedValue -Average).Average
    $util = [math]::Round($avg)
    Write-Output "UTIL=$util"
} else {
    Write-Output "UTIL=0"
}
