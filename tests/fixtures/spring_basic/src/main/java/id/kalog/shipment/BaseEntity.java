package id.kalog.shipment;
/** Base class for entities. */
@MappedSuperclass
public class BaseEntity {
    @Id
    @GeneratedValue
    private Long id;
}
