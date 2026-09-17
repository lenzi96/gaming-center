# Maintainer: Julian
pkgname=gaming-center-git
_pkgname=gaming-center
pkgver=1.2.0
pkgrel=1
pkgdesc="Linux Game Service Center mit PCGamingWiki Integration"
arch=('any')
license=('GPL3')
depends=('python' 'python-pyqt6' 'xdg-utils')
makedepends=('git' 'python-build' 'python-installer' 'python-wheel' 'python-setuptools')
provides=("$_pkgname")
conflicts=("$_pkgname")
source=()

package() {
    cd "$srcdir/.."
    install -d "$pkgdir/usr/share/$_pkgname"
    cp -r gaming_center "$pkgdir/usr/share/$_pkgname/"
    install -Dm755 main.py "$pkgdir/usr/share/$_pkgname/main.py"
    install -Dm755 gaming-center "$pkgdir/usr/bin/gaming-center"
    install -Dm644 gaming-center.desktop "$pkgdir/usr/share/applications/gaming-center.desktop"
    install -Dm644 gaming_center/resources/gaming-center.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/gaming-center.svg"
    install -Dm644 gaming_center/resources/app_icon_256.png "$pkgdir/usr/share/pixmaps/gaming-center.png"
}
