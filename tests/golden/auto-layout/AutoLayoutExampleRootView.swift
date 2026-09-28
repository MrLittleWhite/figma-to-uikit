import UIKit

final class AutoLayoutExampleRootView: UIView {
    private let node0 = UIView()
    private let node1 = UIView()
    private let node2 = UIView()
    private let node3 = UIView()
    private let node4 = UIView()

    override init(frame: CGRect) {
        super.init(frame: frame)
        self.backgroundColor = .systemBackground
        node0.translatesAutoresizingMaskIntoConstraints = false
        self.addSubview(node0)
        node0.isHidden = false
        node1.translatesAutoresizingMaskIntoConstraints = false
        node0.addSubview(node1)
        node1.isHidden = false
        node2.translatesAutoresizingMaskIntoConstraints = false
        node0.addSubview(node2)
        node2.isHidden = false
        node3.translatesAutoresizingMaskIntoConstraints = false
        node2.addSubview(node3)
        node3.isHidden = false
        node4.translatesAutoresizingMaskIntoConstraints = false
        node2.addSubview(node4)
        node4.isHidden = false
        node0.leadingAnchor.constraint(equalTo: self.leadingAnchor, constant: 24).isActive = true
        node0.trailingAnchor.constraint(equalTo: self.trailingAnchor, constant: -24).isActive = true
        node0.topAnchor.constraint(equalTo: self.topAnchor, constant: 40).isActive = true
        node0.heightAnchor.constraint(equalToConstant: 240).isActive = true
        node1.leadingAnchor.constraint(equalTo: node0.centerXAnchor, constant: -86).isActive = true
        node1.bottomAnchor.constraint(equalTo: node0.bottomAnchor, constant: -30).isActive = true
        node1.widthAnchor.constraint(equalToConstant: 60).isActive = true
        node1.heightAnchor.constraint(equalToConstant: 40).isActive = true
        node2.leadingAnchor.constraint(equalTo: node1.trailingAnchor, constant: 12).isActive = true
        node2.bottomAnchor.constraint(equalTo: node0.bottomAnchor, constant: -30).isActive = true
        node2.widthAnchor.constraint(equalToConstant: 120).isActive = true
        node2.heightAnchor.constraint(equalToConstant: 180).isActive = true
        node3.topAnchor.constraint(equalTo: node2.bottomAnchor, constant: -102).isActive = true
        node3.centerXAnchor.constraint(equalTo: node2.centerXAnchor, constant: 10).isActive = true
        node3.widthAnchor.constraint(equalToConstant: 30).isActive = true
        node3.heightAnchor.constraint(equalToConstant: 20).isActive = true
        node4.topAnchor.constraint(equalTo: node3.bottomAnchor, constant: 12).isActive = true
        node4.centerXAnchor.constraint(equalTo: node2.centerXAnchor, constant: 10).isActive = true
        node4.widthAnchor.constraint(equalToConstant: 50).isActive = true
        node4.heightAnchor.constraint(equalToConstant: 40).isActive = true
    }



    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}
