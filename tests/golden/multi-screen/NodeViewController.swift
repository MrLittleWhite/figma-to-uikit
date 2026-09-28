import UIKit

final class NodeViewController: UIViewController {
    private let contentView = NodeRootView()

    override func loadView() {
        view = contentView
    }
}
