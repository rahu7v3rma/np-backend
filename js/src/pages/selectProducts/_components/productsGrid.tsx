import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { useNPConfig } from '@/contexts/npConfig';
import { getProducts } from '@/services/api';
import { Product } from '@/types/product';

import useViewportEntry from '../_hooks/useViewportEntry';

import Filter from './filter';
import Loader from './loader';
import ProductCard from './productCard';

interface Tab {
  id: number;
  idx: number;
  key: number;
  label: string;
  budget: number;
  company_cost: number;
  selectedProductIds?: number[];
}
interface SelectedProductDetails {
  product_id: number;
  discount_mode: string;
  organization_discount_rate?: number | undefined;
}
interface Props {
  formId: number;
  organizationId: number;
  budget: number;
  company_cost: number;
  allTabs: Tab[];
  _default_discount: string;
}
const ProductComponent = ({
  formId,
  organizationId,
  budget,
  company_cost,
  allTabs,
  _default_discount,
}: Props) => {
  const { config } = useNPConfig();
  const currentWizardStep = config?.currentWizardStep || '-1';

  const [loading, setLoading] = useState<boolean>(true);
  const [queryParams, setQueryParams] = useState<{
    page: number;
    priceMin?: number;
    priceMax?: number;
    profitMin?: number;
    profitMax?: number;
    organizationPriceMin?: number;
    organizationPriceMax?: number;
    brandId?: number;
    supplierId?: number;
    categoryId?: number;
    tagIds?: number[];
    employeeGroupId?: number;
    productKind?: string;
    quickOfferId?: number;
    query?: string;
    selectedProductsIds?: number[];
    googlePriceMin?: number;
    googlePriceMax?: number;
  }>({ page: 1 });
  const [products, setProducts] = useState<Product[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [selectedProductIds, setSelectedProductIds] = useState<number[]>([]);
  const [selectAll, setSelectAll] = useState<boolean>(false);
  const [productCompanyCosts, setProductCompanyCosts] = useState<{
    [productId: number]: number;
  }>({});

  const gridEndRef = useRef<HTMLDivElement>(null);
  const baseSPAAssetsUrl = config?.baseSPAAssetsUrl;
  const [updatedTabs, setUpdatedTabs] = useState<Tab[]>([]);
  const [campaignId, setCampaignId] = useState<number | undefined>(undefined);

  const campaignType = useMemo(() => {
    return config?.data
      ? JSON.parse(config?.data.replace(/&quot;/g, '"') || '{}')?.type || null
      : null;
  }, [config]);

  useEffect(() => {
    if (config?.data !== '{}') {
      const id = JSON.parse(
        config?.data.replace(/&quot;/g, '"') || '{}',
      )?.campaign_id;
      if (id) {
        setCampaignId(id);
      }
    }
  }, [config]);

  useEffect(() => {
    const updatedTab = allTabs
      .map((each) => {
        if (config?.data !== '{}') {
          const productDetails = JSON.parse(
            config?.data.replace(/&quot;/g, '"') || '{}',
          )?.products?.[each?.idx];

          if (productDetails) {
            const productIds = productDetails.map(
              (p: SelectedProductDetails) => p['product_id'],
            );

            if (productIds.length > 0) {
              return { ...each, selectedProductIds: productIds };
            }
          }
        }
        return each;
      })
      .filter((each) => each.idx !== formId);

    setUpdatedTabs(updatedTab);
  }, [config, formId, allTabs]);

  useEffect(() => {
    if (config?.data !== '{}') {
      const productDetails = JSON.parse(
        config?.data.replace(/&quot;/g, '"') || '{}',
      )?.products?.[formId];
      if (productDetails) {
        const productIds = productDetails.map(
          (p: SelectedProductDetails) => p['product_id'],
        );
        if (productIds) {
          setSelectedProductIds(productIds);
        }

        // Initialize individual product company costs if they exist
        const initialCompanyCosts: { [productId: number]: number } = {};
        productDetails.forEach(
          (product: SelectedProductDetails & { company_cost?: number }) => {
            if (product.company_cost !== undefined) {
              initialCompanyCosts[product.product_id] = product.company_cost;
            }
          },
        );
        setProductCompanyCosts(initialCompanyCosts);
      }
    }
  }, [config, formId]);

  const fetchProducts = useCallback(
    async (all = false) => {
      setLoading(true);

      try {
        const productsPage: {
          page_data: Product[];
          has_more: boolean;
        } = await getProducts(
          10,
          queryParams.page,
          organizationId,
          queryParams.priceMin,
          queryParams.priceMax,
          queryParams.organizationPriceMin,
          queryParams.organizationPriceMax,
          queryParams.brandId,
          queryParams.supplierId,
          queryParams.categoryId,
          queryParams.tagIds,
          campaignId,
          queryParams.employeeGroupId,
          queryParams.productKind,
          queryParams.quickOfferId,
          queryParams.query,
          queryParams.selectedProductsIds,
          queryParams.googlePriceMin,
          queryParams.googlePriceMax,
        );

        let has_more = productsPage.has_more;
        let page = queryParams.page + 1;
        let products = [...productsPage.page_data];
        let productsPageResponse = [];
        if (all) {
          while (has_more) {
            productsPageResponse = await getProducts(
              10,
              page,
              organizationId,
              queryParams.priceMin,
              queryParams.priceMax,
              queryParams.organizationPriceMin,
              queryParams.organizationPriceMax,
              queryParams.brandId,
              queryParams.supplierId,
              queryParams.categoryId,
              queryParams.tagIds,
              campaignId,
              queryParams.employeeGroupId,
              queryParams.productKind,
              queryParams.quickOfferId,
              queryParams.query,
              queryParams.selectedProductsIds,
              queryParams.googlePriceMin,
              queryParams.googlePriceMax,
            );
            has_more = productsPageResponse.has_more;
            page += 1;
            products = [...products, ...productsPageResponse.page_data];
          }
          products = [...products, ...productsPage.page_data];
          productsPage.page_data = products;
          productsPage.has_more = false;
        }

        // Filter products by Company Cost Per Employee (local filtering)
        if (
          queryParams.organizationPriceMin ||
          queryParams.organizationPriceMax
        ) {
          productsPage.page_data = productsPage.page_data.filter((product) => {
            const productCompanyCost = getProductCompanyCost(product.id);

            if (
              queryParams.organizationPriceMin &&
              productCompanyCost < queryParams.organizationPriceMin
            ) {
              return false;
            }
            if (
              queryParams.organizationPriceMax &&
              productCompanyCost > queryParams.organizationPriceMax
            ) {
              return false;
            }
            return true;
          });
        }

        // apply the profit filter
        if (queryParams.profitMax !== undefined) {
          productsPage.page_data = productsPage.page_data.filter((product) => {
            const productCompanyCost = getProductCompanyCost(product.id);
            return (
              ((productCompanyCost - product.total_cost) / productCompanyCost) *
                100 <=
              (queryParams.profitMax as number)
            );
          });
        }
        if (queryParams.profitMin !== undefined) {
          productsPage.page_data = productsPage.page_data.filter((product) => {
            const productCompanyCost = getProductCompanyCost(product.id);
            return (
              ((productCompanyCost - product.total_cost) / productCompanyCost) *
                100 >=
              (queryParams.profitMin as number)
            );
          });
        }

        // sort each product's images array so that the main image is first
        for (const product of productsPage.page_data as Product[]) {
          product.images?.sort((a, b) => Number(b?.main) - Number(a?.main));
        }

        setProducts((prevProducts) => {
          if (selectAll) {
            setSelectedProductIds((prevSelectedProductIds) => [
              ...prevSelectedProductIds,
              ...[...prevProducts, ...productsPage.page_data]
                .map((product) => product.id)
                .filter((id) => !prevSelectedProductIds.includes(id)),
            ]);
          }
          if (queryParams.page === 1) {
            return productsPage.page_data;
          }
          return [
            ...prevProducts,
            ...productsPage.page_data.filter(
              (product) =>
                !prevProducts
                  .map((prev_product) => prev_product.id)
                  .includes(product.id),
            ),
          ];
        });
        setHasMore(productsPage.has_more);
      } catch (error) {
        setProducts([]);
      } finally {
        setLoading(false);
      }
    },
    [
      queryParams,
      organizationId,
      selectAll,
      campaignId,
      productCompanyCosts,
      company_cost,
    ],
  );

  useEffect(() => {
    // fetch products on page mount
    fetchProducts();
  }, [fetchProducts]);

  const setSearchParam = useCallback((key: string, value: string) => {
    const searchParams = new URLSearchParams(window.location.search);
    searchParams.set(key, value);
    window.history.pushState(
      undefined,
      '',
      `${window.location.pathname}?${searchParams.toString()}`,
    );
  }, []);

  const getSearchParam = useCallback((key: string) => {
    const searchParams = new URLSearchParams(window.location.search);
    return searchParams.get(key);
  }, []);

  const onProductClick = useCallback(
    (productId: number, selected: boolean) => {
      if (!selected) {
        const ids = selectedProductIds.filter(
          (id) => id !== productId && id !== undefined,
        );
        setSelectedProductIds(ids);
        setSearchParam('productSelectionIds', ids.join(','));
      } else {
        const ids = [
          ...selectedProductIds.filter(
            (id) => id !== undefined && id !== productId,
          ),
          productId,
        ];
        setSelectedProductIds(ids);
        setSearchParam('productSelectionIds', ids.join(','));
      }
    },
    [selectedProductIds, setSearchParam],
  );

  const handleRemoveProduct = useCallback(
    (productId: number) => {
      setSelectedProductIds(
        selectedProductIds.filter((id) => id !== productId),
      );
    },
    [selectedProductIds],
  );

  const handleApplyFilter = useCallback(
    (
      priceMin?: number,
      priceMax?: number,
      organizationPriceMin?: number,
      organizationPriceMax?: number,
      profitMin?: number,
      profitMax?: number,
      brandId?: number,
      supplierId?: number,
      categoryId?: number,
      tagIds?: number[],
      employeeGroupId?: number,
      productKind?: string,
      quickOfferId?: number,
      query?: string,
      selectedProducts?: boolean,
      googlePriceMin?: number,
      googlePriceMax?: number,
    ) => {
      setSelectAll(false);
      setQueryParams({
        priceMin,
        priceMax,
        organizationPriceMin,
        organizationPriceMax,
        profitMin,
        profitMax,
        brandId,
        supplierId,
        categoryId,
        tagIds,
        employeeGroupId,
        productKind,
        quickOfferId,
        query,
        selectedProductsIds: selectedProducts ? selectedProductIds : undefined,
        page: 1,
        googlePriceMin,
        googlePriceMax,
      });
    },
    [selectedProductIds],
  );

  const handleGridScrolledToEnd = useCallback(() => {
    if (hasMore && !loading) {
      setQueryParams((prevParams) => {
        const searchParams = new URLSearchParams(window.location.search);
        const searchParamsPage =
          Number(searchParams.get('productSelectionPage')) || 0;
        searchParams.set(
          'productSelectionPage',
          String(Math.max(searchParamsPage, prevParams.page + 1)),
        );
        window.history.pushState(
          {},
          '',
          `${window.location.pathname}?${searchParams.toString()}`,
        );

        return {
          ...prevParams,
          page: prevParams.page + 1,
        };
      });
    }
  }, [hasMore, loading]);

  const handleSelectAllProducts = async (
    e: React.SyntheticEvent<HTMLButtonElement>,
  ) => {
    e.preventDefault();
    if (!selectAll) {
      await fetchProducts(true);
      if (!selectAll) {
        setSelectedProductIds([
          ...selectedProductIds,
          ...products
            .map((product) => product.id)
            .filter((id) => !selectedProductIds.includes(id)),
        ]);
        setSelectAll(true);
        return;
      }
    }
    setSelectedProductIds([]);
    setSelectAll(false);
  };

  // "subscribe" to events of the component at the end of the products grid
  // coming into the viewport so we can load the next products page if there is
  // one
  useViewportEntry(gridEndRef, handleGridScrolledToEnd);

  useEffect(() => {
    const searchParams = new URLSearchParams(window.location.search);
    const searchParamsPage = Number(searchParams.get('productSelectionPage'));
    if (queryParams.page < searchParamsPage) {
      setQueryParams((prevParams) => ({
        ...prevParams,
        page: prevParams.page + 1,
      }));
    }
  }, [queryParams]);

  useEffect(() => {
    const productSelectionIds = getSearchParam('productSelectionIds');
    if (productSelectionIds) {
      setSelectedProductIds(productSelectionIds.split(',').map(Number));
    }
  }, [getSearchParam]);

  const handleValueChange = useCallback(
    (_product_id: number, _value: number) => {
      // Simplified voucher logic - Company Cost Per Employee is now used directly
      // No longer need to calculate organization discount rates
    },
    [],
  );

  // Handler to update individual product company cost
  const handleProductCompanyCostChange = useCallback(
    (productId: number, newCost: number) => {
      setProductCompanyCosts((prev) => ({
        ...prev,
        [productId]: newCost,
      }));
    },
    [],
  );

  // Function to get company cost for a specific product (individual or default)
  const getProductCompanyCost = useCallback(
    (productId: number) => {
      return productCompanyCosts[productId] ?? company_cost;
    },
    [productCompanyCosts, company_cost],
  );

  return (
    <>
      <div className="flex gap-6">
        <div className="min-w-64">
          <Filter
            applyFilter={handleApplyFilter}
            budget={budget}
            company_cost={company_cost}
            selectedProductIds={selectedProductIds}
            products={products}
            baseSPAAssetsUrl={baseSPAAssetsUrl}
            handleRemoveProduct={handleRemoveProduct}
            handleSelectAllProducts={handleSelectAllProducts}
            selectedEmpGroups={updatedTabs}
            selectAll={selectAll}
          />
        </div>
        {loading && queryParams.page === 1 ? (
          <div className="w-full h-full flex">
            <div className="m-auto w-fit">
              <Loader />
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5 gap-4">
            {products.map((p) => {
              return (
                <ProductCard
                  key={`product-${p.id}`}
                  image={p.images.length > 0 ? p.images[0].image : undefined}
                  total_cost={p.total_cost}
                  google_price={p.google_price}
                  brandImage={p.brand.logo_image}
                  name={p.name}
                  organization_price={getProductCompanyCost(p.id)}
                  value_price={
                    p.product_kind === 'MONEY' ? getProductCompanyCost(p.id) : 0
                  }
                  voucher_type={p.voucher_type}
                  discountMode="EMPLOYEE"
                  _handleDiscountModeChange={() => {}}
                  productKind={p.product_kind}
                  handleValueChange={handleValueChange}
                  handleProductCompanyCostChange={
                    handleProductCompanyCostChange
                  }
                  ordered_quantity={p.ordered_quantity}
                  id={p.id}
                  _setProducts={setProducts}
                  is_selected={selectedProductIds.includes(p.id)}
                  onProductClick={onProductClick}
                />
              );
            })}
            {!loading && <div ref={gridEndRef} className="w-[1px] h-[1px]" />}
          </div>
        )}
      </div>
      <input
        type="hidden"
        name={`${currentWizardStep}-${formId.toString()}-${campaignType === 'quick_offer' ? 'products' : 'campaign_data'}`}
        value={JSON.stringify({
          selected_products: selectedProductIds,
          discount_modes: selectedProductIds.reduce(
            (acc, productId) => {
              acc[productId] = 'EMPLOYEE';
              return acc;
            },
            {} as { [key: string]: string },
          ),
          company_costs: selectedProductIds.reduce(
            (acc, productId) => {
              acc[productId] = getProductCompanyCost(productId);
              return acc;
            },
            {} as { [key: string]: number },
          ),
        })}
      />
    </>
  );
};

export default ProductComponent;
