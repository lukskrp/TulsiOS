# Windows programs

Many Windows programs and games run on TulsiOS through **Wine**, which translates
what they ask of Windows, and **Proton**, Valve's version of Wine for games. You don't
use them directly. These apps do it for you:

| You want to | Use |
| --- | --- |
| Run a Windows program (a .exe or .msi) | **Bottles** |
| Play games from GOG, Epic, Humble, or emulators | **Lutris** |
| Play your Steam games | **Steam** (Proton is built in) |

The installer offers Bottles and Lutris on its "Extra software" page. Otherwise
install them from the Software Center: both are on its **Featured** page.

## Bottles

Bottles keeps each Windows program in its own **bottle**: its own Windows folders,
the version of Wine or Proton that suits it, and the Windows parts it needs (.NET,
Visual C++, fonts). A program that breaks one bottle can't break another.

- **Running a program:** double-click the downloaded `.exe` or `.msi`. TulsiOS says
  it's a Windows program and offers **Open with Bottles**, or to install Bottles
  first. Bottles then asks which bottle to run it in, or makes a new one.
- **Making a bottle yourself:** open Bottles and choose **Create New Bottle**. Pick
  **Application** for programs, or **Gaming** for games (it adds what games usually
  need). Then **Run Executable…** runs an installer inside it.
- **Snapshots:** Bottles can save a bottle's state (**Snapshots**) and go back to it,
  if an installer or an update breaks something.
- **On first start,** Bottles says it isn't the Flatpak build its makers support.
  That's true. TulsiOS's build works the same; report problems to TulsiOS rather than
  to Bottles.

Bottles is free software, made by its community:
<https://usebottles.com/funding/>.

## Lutris

Lutris keeps your games in one library: from GOG, Epic, Steam, Humble and others,
plus emulators for older consoles. Its community writes install scripts for many
games, which set up Wine or Proton for you. Search for a game on
[lutris.net](https://lutris.net), or add one from a store you sign in to.

## Steam

Steam is unfree, so it isn't in the Software Center by default. To install it, add
these lines with `tulsi config`:

```nix
programs.steam.enable = true;
nixpkgs.config.allowUnfree = true;
```

In Steam, **Settings › Compatibility › Enable Steam Play for all other titles** runs
Windows games with Proton.

## ⚠ Windows programs run as you

Wine is not a sandbox. A Windows program can read and change everything in your home
folder, as any program you run can. Install Windows programs only from their makers,
and only ones you trust. TulsiOS's File History (if it's on) can bring back files a
bad program changed.
