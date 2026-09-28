import UIKit

final class HomeRootView: UIView {
    var onInteraction: ((GeneratedInteraction) -> Void)?
    private let node0 = UIView()
    private let node1 = UILabel()
    private let node2 = UIButton(type: .system)
    private let node3 = UIImageView()

    override init(frame: CGRect) {
        super.init(frame: frame)
        self.backgroundColor = UIColor(red: 1.00000000, green: 1.00000000, blue: 1.00000000, alpha: 1.00000000)
        node0.translatesAutoresizingMaskIntoConstraints = false
        self.addSubview(node0)
        node0.isHidden = false
        node1.translatesAutoresizingMaskIntoConstraints = false
        node1.text = "你好 Home"; node1.numberOfLines = 0
        node0.addSubview(node1)
        node1.isHidden = false
        node1.font = UIFont(name: "System", size: 16.0) ?? UIFont.systemFont(ofSize: 16.0)
        node2.translatesAutoresizingMaskIntoConstraints = false
        node0.addSubview(node2)
        node2.addTarget(self, action: #selector(handleNode2Tap), for: .touchUpInside)
        node2.isHidden = false
        node3.translatesAutoresizingMaskIntoConstraints = false
        node0.addSubview(node3)
        node3.isHidden = false
        node0.leadingAnchor.constraint(equalTo: self.leadingAnchor, constant: 16.0).isActive = true
        node0.topAnchor.constraint(equalTo: self.topAnchor, constant: 24.0).isActive = true
        node0.widthAnchor.constraint(equalToConstant: 358.0).isActive = true
        node0.heightAnchor.constraint(equalToConstant: 200.0).isActive = true
        node1.leadingAnchor.constraint(equalTo: node0.leadingAnchor, constant: 12.0).isActive = true
        node1.topAnchor.constraint(equalTo: node0.topAnchor, constant: 16.0).isActive = true
        node1.widthAnchor.constraint(equalToConstant: 200.0).isActive = true
        node1.heightAnchor.constraint(equalToConstant: 24.0).isActive = true
        node2.leadingAnchor.constraint(equalTo: node0.leadingAnchor, constant: 12.0).isActive = true
        node2.topAnchor.constraint(equalTo: node0.topAnchor, constant: 56.0).isActive = true
        node2.widthAnchor.constraint(equalToConstant: 120.0).isActive = true
        node2.heightAnchor.constraint(equalToConstant: 44.0).isActive = true
        node3.leadingAnchor.constraint(equalTo: node0.leadingAnchor, constant: 184.0).isActive = true
        node3.topAnchor.constraint(equalTo: node0.topAnchor, constant: 16.0).isActive = true
        node3.widthAnchor.constraint(equalToConstant: 32.0).isActive = true
        node3.heightAnchor.constraint(equalToConstant: 32.0).isActive = true
    }

    @objc private func handleNode2Tap() {
        onInteraction?(GeneratedInteraction(sourceID: "next", trigger: "ON_CLICK", action: "NODE", destinationID: "screen-2"))
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}
