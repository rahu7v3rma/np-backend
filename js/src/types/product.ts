export type Product = {
  id: number;
  name: string;
  total_cost: number;
  google_price?: number;
  product_kind: string;
  brand: Brand;
  supplier: Supplier;
  images: ProductImage[];
  calculated_price: number;
  voucher_type: string | null;
  client_discount_rate: number;
  ordered_quantity: number;
};

type Brand = {
  name: string;
  logo_image: string;
};

type Supplier = {
  name: string;
};

type ProductImage = {
  main: boolean;
  image: string;
};
