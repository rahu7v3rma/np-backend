export type Product = {
  id: number;
  name: string;
  total_cost: number;
  google_price?: number;
  brand: Brand;
  supplier: Supplier;
  images: ProductImage[];
  calculated_price: number;
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
