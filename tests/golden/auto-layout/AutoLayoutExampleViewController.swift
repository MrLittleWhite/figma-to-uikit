import UIKit

final class AutoLayoutExampleViewController: UIViewController {
    private let contentView = AutoLayoutExampleRootView()

    override func loadView() {
        view = contentView
    }
}
