package id.kalog.shipment;
@Entity
@Table(name = "shipments")
public class Shipment extends BaseEntity {
    @Column(name = "awb_number")
    @NotEmpty
    private String awb;
    @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;
    @Transient
    private String cache;
}
