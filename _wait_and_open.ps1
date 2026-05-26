# Wait for the local Dash server to start responding on port 8050,
# then open it in the user's default browser. Invoked in the background
# from run.bat so the foreground Python launch is not held up.
#
# A cold first launch on a fresh install can take 10–15 s for Python
# and Dash to load and bind to the port; the previous fixed delay in
# run.bat was too short, so users saw a connection-refused page and
# had to refresh by hand. Polling the TCP port until it accepts a
# connection gives us a launch time that matches whatever the real
# server start time happens to be (essentially zero on warm restarts).
#
# The leading underscore in the filename is a convention that this is
# an internal helper, not something an end user should double-click.

$port    = 8050
$maxIter = 180   # 180 × 500 ms = 90 s upper bound

for ($i = 0; $i -lt $maxIter; $i++) {
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $async  = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        # 250 ms per attempt is plenty for a localhost connect; if the
        # port is open the OS replies immediately. If it isn't open we
        # don't want to block long.
        if ($async.AsyncWaitHandle.WaitOne(250) -and $client.Connected) {
            $client.EndConnect($async)
            $client.Close()
            break
        }
    } catch {
        # Connection refused / network errors — server isn't ready yet.
    } finally {
        if ($client) { $client.Close() }
    }
    Start-Sleep -Milliseconds 500
}

# Launch the URL via cmd's `start` builtin — this is the same path the
# prior run.bat used and is the most reliable way to invoke the
# default-browser ShellExecute handler from a background process. The
# empty "" is the (unused) window title; `start` insists on consuming
# the first quoted token as a title, so a placeholder is required when
# we later pass any other quoted arg. The URL here is unquoted so it
# is treated as the target.
& cmd /c start "" "http://localhost:$port"
