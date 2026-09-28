import UIKit

final class Home_702f965df9d15afc0b7240a8a427d4ca06258b19f90533d5a2919c1580530d33ViewController: UIViewController {
    private let contentView = Home_702f965df9d15afc0b7240a8a427d4ca06258b19f90533d5a2919c1580530d33RootView()
    var onInteraction: ((GeneratedInteraction) -> Void)? {
        didSet { contentView.onInteraction = onInteraction }
    }

    override func loadView() {
        view = contentView
    }
}
