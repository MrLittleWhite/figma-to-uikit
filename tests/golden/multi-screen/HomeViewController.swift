import UIKit

final class HomeViewController: UIViewController {
    private let contentView = HomeRootView()
    var onInteraction: ((GeneratedInteraction) -> Void)? {
        didSet { contentView.onInteraction = onInteraction }
    }

    override func loadView() {
        view = contentView
    }
}
