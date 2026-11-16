# Controlled Windows Forms app for real desktop automation verification.
# Run: powershell -NoProfile -ExecutionPolicy Bypass -File examples/testbench.ps1
param([string]$Title = 'Piko Testbench')
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = $Title
$form.Width = 520
$form.Height = 320
$form.StartPosition = 'CenterScreen'
$nameLabel = New-Object System.Windows.Forms.Label
$nameLabel.Name = 'NameLabel'; $nameLabel.Text = 'Name'; $nameLabel.Location = New-Object System.Drawing.Point(30,35)
$nameInput = New-Object System.Windows.Forms.TextBox
$nameInput.Name = 'NameInput'; $nameInput.AccessibleName = 'NameInput'
$nameInput.Location = New-Object System.Drawing.Point(140,30)
$nameInput.Width = 270
$status = New-Object System.Windows.Forms.Label
$status.Name = 'StatusLabel'
$status.Text = 'Waiting'; $status.Location = New-Object System.Drawing.Point(140,150)
$status.AutoSize = $true
$save = New-Object System.Windows.Forms.Button
$save.Name = 'SaveButton'; $save.AccessibleName = 'SaveButton'
$save.Text = 'Save'; $save.Location = New-Object System.Drawing.Point(140,88)
$save.Add_Click({
    if ([string]::IsNullOrWhiteSpace($nameInput.Text)) {
        $status.Text = 'Error: enter a name'
    } else {
        $status.Text = "Saved: $($nameInput.Text)"
    }
})
$form.Controls.AddRange(@($nameLabel,$nameInput,$save,$status))
[void]$form.ShowDialog()
