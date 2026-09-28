import UIKit

final class Home_702f965df9d15afc0b7240a8a427d4ca06258b19f90533d5a2919c1580530d33RootView: UIView {
    var onInteraction: ((GeneratedInteraction) -> Void)?
    private let node0 = UIView()

    override init(frame: CGRect) {
        super.init(frame: frame)
        self.backgroundColor = .systemBackground
        node0.translatesAutoresizingMaskIntoConstraints = false
        self.addSubview(node0)
        node0.isUserInteractionEnabled = true
        node0.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(handleNode0Tap)))
        node0.isHidden = false
        node0.leadingAnchor.constraint(equalTo: self.leadingAnchor, constant: 0.0).isActive = true
        node0.topAnchor.constraint(equalTo: self.topAnchor, constant: 0.0).isActive = true
        node0.widthAnchor.constraint(equalToConstant: 0.0).isActive = true
        node0.heightAnchor.constraint(equalToConstant: 0.0).isActive = true
    }

    @objc private func handleNode0Tap() {
        onInteraction?(GeneratedInteraction(sourceID: "outside", trigger: "ON_CLICK", action: "NODE", destinationID: "not-captured"))
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}
