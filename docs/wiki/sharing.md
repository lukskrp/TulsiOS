# Sharing files and networks

## LocalSend: files between your devices

**LocalSend** sends files, photos and text between devices on the same network:
phones and computers, Android, iPhone, Windows, macOS and Linux. It needs no account
and no internet. TulsiOS comes with it; find it in the app menu.

1. Install LocalSend on the other device too, from its app store or
   [localsend.org](https://localsend.org).
2. Open LocalSend on both. They find each other on their own.
3. Choose **Send**, pick files, and pick the other device. The other device asks
   whether to accept them.

TulsiOS opens the ports LocalSend needs (53317) in its firewall, so other devices
can find yours. To turn LocalSend off entirely, add
`programs.localsend.enable = false;` with `tulsi config`.

## Tailscale: your devices as one private network

[Tailscale](https://tailscale.com) connects your computers and phones into a private
network, wherever they are, so you can reach one from another. It isn't installed by
default. To install it:

```sh
tulsi service enable tailscale   # installs and starts it (asks for your password)
sudo tailscale up                # prints a link: open it and sign in
tailscale status                 # your devices
```

`tulsi undo` takes it back like any change.

## LibreOffice

The installer can download **LibreOffice** while it installs TulsiOS: tick it on the
"Extra software" page. You can also install it any time from the Software Center.

LibreOffice is free, made by The Document Foundation and thousands of volunteers. If
you use it, consider supporting them: <https://www.libreoffice.org/donate/>. The
Software Center links that page next to LibreOffice too.
