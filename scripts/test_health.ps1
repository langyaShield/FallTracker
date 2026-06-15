$r = Invoke-WebRequest http://localhost:8000/ -UseBasicParsing -TimeoutSec 5
Write-Host "Frontend (via /8000): HTTP $($r.StatusCode), len=$($r.Content.Length)"
$title = (Select-String -InputObject $r.Content -Pattern '<title>(.*)</title>').Matches.Groups[1].Value
Write-Host "Title: $title"

Write-Host "---"
Write-Host "Backend /api/..."
try {
  $r2 = Invoke-WebRequest http://localhost:8000/api/auth/me -UseBasicParsing -TimeoutSec 5
  Write-Host "GET /api/auth/me: HTTP $($r2.StatusCode)"
} catch { Write-Host "GET /api/auth/me: $_" }

Write-Host "---"
Write-Host "Backend /api/notifications (should be 401 unauth)..."
try {
  $r3 = Invoke-WebRequest http://localhost:8000/api/notifications -UseBasicParsing -TimeoutSec 5
  Write-Host "GET /api/notifications: HTTP $($r3.StatusCode)"
} catch { Write-Host "GET /api/notifications: $_" }
