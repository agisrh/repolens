package id.kalog.shipment;

/**
 * REST endpoints for shipments. This class for tracking is used by the mobile app.
 */
@RestController
@RequestMapping("/api/shipments")
public class ShipmentController {
    @GetMapping
    public List<Shipment> list() { return null; }

    @GetMapping("/{awb}")
    public Shipment detail(@PathVariable String awb) { return null; }

    @PostMapping(value = "/{awb}/cancel", produces = "application/json")
    public void cancel(@PathVariable String awb) {}

    @RequestMapping(path = "/sync", method = {RequestMethod.PUT, RequestMethod.PATCH})
    public void sync() {}
}
