import XCTest
import UIKit
@testable import UIKitSmoke

final class GeneratedLayoutTests: XCTestCase {
    // Inspect only fixture-owned nodes, never UIButton's implementation subviews.
    @MainActor
    private func withHosted(_ child: UIViewController, body: (UIView) throws -> Void) rethrows {
        let previous = UIApplication.shared.windows.first(where: { $0.isKeyWindow })
        let window = UIWindow(frame: UIScreen.main.bounds)
        let container = UIViewController()
        window.rootViewController = container
        window.makeKeyAndVisible()
        container.loadViewIfNeeded()
        container.addChild(child)
        child.loadViewIfNeeded()
        child.view.translatesAutoresizingMaskIntoConstraints = true
        child.view.autoresizingMask = []
        container.view.addSubview(child.view)
        child.didMove(toParent: container)
        defer {
            child.willMove(toParent: nil)
            child.view.removeFromSuperview()
            child.removeFromParent()
            window.isHidden = true
            window.rootViewController = nil
            previous?.makeKeyAndVisible()
        }
        XCTAssertNotNil(child.view.window)
        try body(child.view)
    }

    @MainActor
    private func check(_ view: UIView, _ expected: CGRect, file: StaticString = #filePath, line: UInt = #line) {
        let actual = view.frame
        // Auto Layout aligns view edges to the hosting display's pixel grid.
        // Round independent expected edges, not width/height (which can span two rounded edges).
        guard let scale = view.window?.screen.scale else {
            XCTFail("Expected a real hosting window", file: file, line: line)
            return
        }
        func pixel(_ value: CGFloat) -> CGFloat { (value * scale).rounded() / scale }
        let aligned = CGRect(x: pixel(expected.minX), y: pixel(expected.minY),
                             width: pixel(expected.maxX) - pixel(expected.minX),
                             height: pixel(expected.maxY) - pixel(expected.minY))
        for (value, target) in zip([actual.minX, actual.minY, actual.width, actual.height],
                                   [aligned.minX, aligned.minY, aligned.width, aligned.height]) {
            XCTAssertTrue(value.isFinite, file: file, line: line)
            XCTAssertEqual(value, target, accuracy: 0.1, file: file, line: line)
        }
        XCTAssertFalse(view.hasAmbiguousLayout, file: file, line: line)
    }

    @MainActor
    func testResponsiveLayoutRoundTrip() throws {
        withHosted(ResponsiveExampleViewController()) { root in
            XCTAssertEqual(root.subviews.count, 4)
            guard root.subviews.count == 4 else { return }
            XCTAssertTrue(root.subviews[3] is UIButton)
            for size in [CGSize(width: 390, height: 844), CGSize(width: 430, height: 932),
                         CGSize(width: 390, height: 844)] {
                root.frame = CGRect(origin: .zero, size: size)
                root.setNeedsLayout()
                root.layoutIfNeeded()
                XCTAssertEqual(root.bounds.size, size)
                XCTAssertFalse(root.hasAmbiguousLayout)
                let w = size.width, h = size.height
                // Independent UIKit control: constant constraints, no generated SCALE guide.
                // This verifies the edge-rounding assumption on the actual hosting screen.
                let probe = UIView()
                probe.translatesAutoresizingMaskIntoConstraints = false
                root.superview!.addSubview(probe)
                NSLayoutConstraint.activate([
                    probe.leadingAnchor.constraint(equalTo: root.superview!.leadingAnchor, constant: w * 0.1),
                    probe.topAnchor.constraint(equalTo: root.superview!.topAnchor, constant: h * 0.2),
                    probe.widthAnchor.constraint(equalToConstant: w * 0.3),
                    probe.heightAnchor.constraint(equalToConstant: h * 0.2)
                ])
                root.superview!.layoutIfNeeded()
                print("Pixel control size=\(size) scale=\(root.window!.screen.scale) native=\(probe.frame) generated=\(root.subviews[2].frame)")
                check(probe, CGRect(x: w * 0.1, y: h * 0.2, width: w * 0.3, height: h * 0.2))
                probe.removeFromSuperview()
                check(root.subviews[0], CGRect(x: 24, y: 40, width: w - 48, height: 80))
                check(root.subviews[1], CGRect(x: w / 2 - 30, y: h / 2 - 30, width: 60, height: 60))
                check(root.subviews[2], CGRect(x: w * 0.1, y: h * 0.2, width: w * 0.3, height: h * 0.2))
                check(root.subviews[3], CGRect(x: w - 144, y: h - 76, width: 120, height: 44))
            }
        }
    }

    @MainActor
    func testAutoLayoutRoundTrip() throws {
        withHosted(AutoLayoutExampleViewController()) { root in
            XCTAssertEqual(root.subviews.count, 1)
            guard let row = root.subviews.first, row.subviews.count == 2 else {
                XCTFail("Missing flow fixture hierarchy"); return
            }
            let box = row.subviews[0], column = row.subviews[1]
            XCTAssertEqual(column.subviews.count, 2)
            guard column.subviews.count == 2 else { return }
            for size in [CGSize(width: 390, height: 844), CGSize(width: 430, height: 932),
                         CGSize(width: 390, height: 844)] {
                root.frame = CGRect(origin: .zero, size: size)
                root.setNeedsLayout()
                root.layoutIfNeeded()
                XCTAssertFalse(root.hasAmbiguousLayout)
                check(row, CGRect(x: 24, y: 40, width: size.width - 48, height: 240))
                // Independent fixture arithmetic: 192-point group, padding center shifted +10.
                let firstX: CGFloat = size.width == 390 ? 85 : 105
                check(box, CGRect(x: firstX, y: 170, width: 60, height: 40))
                check(column, CGRect(x: firstX + 72, y: 30, width: 120, height: 180))
                check(column.subviews[0], CGRect(x: 55, y: 78, width: 30, height: 20))
                check(column.subviews[1], CGRect(x: 45, y: 110, width: 50, height: 40))
                XCTAssertEqual(column.frame.minX - box.frame.maxX, 12, accuracy: 0.1)
                XCTAssertEqual(column.subviews[1].frame.minY - column.subviews[0].frame.maxY, 12, accuracy: 0.1)
            }
        }
    }

    @MainActor
    func testPackagedImageDecodes() throws {
        try withHosted(AssetExampleViewController()) { root in
            root.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
            root.setNeedsLayout()
            root.layoutIfNeeded()
            XCTAssertEqual(root.subviews.count, 1)
            let imageView = try XCTUnwrap(root.subviews.first as? UIImageView)
            let image = try XCTUnwrap(imageView.image)
            let pixels = try XCTUnwrap(image.cgImage)
            XCTAssertEqual(pixels.width, 2)
            XCTAssertEqual(pixels.height, 3)
            XCTAssertEqual(image.size, CGSize(width: 2, height: 3))
            // Force actual pixel decompression, not merely catalog lookup.
            let context = try XCTUnwrap(CGContext(data: nil, width: 2, height: 3,
                bitsPerComponent: 8, bytesPerRow: 8, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            context.draw(pixels, in: CGRect(x: 0, y: 0, width: 2, height: 3))
            let bytes = try XCTUnwrap(context.data).assumingMemoryBound(to: UInt8.self)
            XCTAssertEqual(bytes[0], 255)
            XCTAssertEqual(bytes[3], 255)
            check(imageView, CGRect(x: 24, y: 40, width: 32, height: 48))
        }
    }
}
