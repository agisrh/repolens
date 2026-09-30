export const shipments = pgTable('shipments', {
  id: serial('id').primaryKey(),
  awb: text('awb').notNull().unique(),
  status: text('status'),
});
