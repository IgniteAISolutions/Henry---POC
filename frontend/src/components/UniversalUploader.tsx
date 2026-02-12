// src/components/UniversalUploader.tsx
// EarthFare Eco Supermarket - Product Automation
import React, { useRef, useState } from 'react';

type Product = {
  id: string;
  name: string;
  brand: string;
  sku: string;
  barcode?: string;
  category?: string;
  source?: string;
  specifications?: Record<string, any>;
  features?: string[];
  descriptions?: {
    shortDescription: string;
    longDescription: string;
    metaDescription: string;
    title?: string;
    body_html?: string;
  };
  dietary_preferences?: string[];
  dietary_info?: string[];
  allergens?: {
    contains?: string[];
    may_contain?: string[];
    free_from?: string[];
  };
  ingredients?: string;
  ingredients_source?: string;
  nutrition?: {
    energy_kcal?: string;
    energy_kj?: string;
    fat?: string;
    saturates?: string;
    carbohydrates?: string;
    sugars?: string;
    fibre?: string;
    protein?: string;
    salt?: string;
  };
  nutrition_source?: string;
  data_sources?: string[];
  data_source_url?: string;
  images?: string[];
  price?: string | null;
};

type Step = 'input' | 'processing' | 'complete';
type Tab = 'csv' | 'manual-codes' | 'website-url';

// EarthFare grocery categories - 9 Main Categories (matching Vector/Shopify)
type Category =
  | 'Groceries'
  | 'Fresh'
  | 'Drinks'
  | 'Frozen'
  | 'Household and Non-Food'
  | 'Body Care'
  | 'Health'
  | 'Promo and Seasonal'
  | 'Earthfare Kitchen';

const CATEGORY_OPTIONS: readonly Category[] = [
  'Groceries',
  'Fresh',
  'Drinks',
  'Frozen',
  'Household and Non-Food',
  'Body Care',
  'Health',
  'Promo and Seasonal',
  'Earthfare Kitchen',
] as const;

// EarthFare brand colors
const COLORS = {
  primary: '#2d5a27',      // Deep forest green
  primaryLight: '#4a7c44', // Lighter green
  primaryDark: '#1e3d1a',  // Darker green
  secondary: '#8bc34a',    // Fresh lime green
  accent: '#f9a825',       // Warm amber
  background: '#f5f7f3',   // Light sage
  cardBg: '#ffffff',
  text: '#2c3e2a',
  textLight: '#5d6b5a',
  border: '#d4ddd2',
  success: '#43a047',
  warning: '#ff9800',
  error: '#e53935',
};

const API_BASE =
  process.env.REACT_APP_API_BASE ||
  (process.env.REACT_APP_BACKEND_URL ? process.env.REACT_APP_BACKEND_URL + '/api' : '') ||
  '/api';

console.log('EarthFare API URL:', API_BASE);

const BORDER_THIN = `1px solid ${COLORS.border}`;
const INPUT_BASE = {
  width: '100%',
  padding: '12px',
  border: BORDER_THIN,
  borderRadius: '8px',
  fontSize: '1rem',
  backgroundColor: COLORS.cardBg,
} as const;

const toMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

function normaliseExtractResponse(json: any): any[] {
  if (!json) return [];
  if (Array.isArray(json?.products)) return json.products;
  if (Array.isArray(json?.data?.products)) return json.data.products;
  if (Array.isArray(json?.data)) return json.data;
  return [];
}

async function postJson(path: string, body: any, timeoutMs: number = 120000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}/${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.REACT_APP_DOCLING_API_KEY || '',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const text = await res.text();
    console.log(`[${path}] Response:`, { status: res.status, text: text.substring(0, 200) });

    let json: any = null;
    try { json = JSON.parse(text); } catch {}

    if (!res.ok) {
      throw new Error(json?.error || json?.detail || `${path} failed ${res.status}`);
    }
    return json;
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('Request timed out. Please try again or contact support.');
    }
    throw error;
  }
}

async function postForm(path: string, form: FormData, timeoutMs: number = 600000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}/${path}`, {
      method: 'POST',
      headers: {
        'x-api-key': process.env.REACT_APP_DOCLING_API_KEY || '',
      },
      body: form,
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    const text = await res.text();
    console.log(`[${path}] Response:`, { status: res.status, text: text.substring(0, 200) });

    let json: any = null;
    try { json = JSON.parse(text); } catch {}

    if (!res.ok) {
      throw new Error(json?.error || json?.detail || `${path} failed ${res.status}`);
    }
    return json;
  } catch (error: any) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error('Request timed out. Large files may take up to 10 minutes.');
    }
    throw error;
  }
}

async function processCSV(file: File, category: Category, brandUrl: string, onProgress: (msg: string) => void): Promise<Product[]> {
  console.log('[CSV] Starting...');
  onProgress('Uploading CSV...');

  const formData = new FormData();
  formData.append('file', file, file.name);
  formData.append('category', category);

  // Add brand URL if provided - used to scrape manufacturer website for nutrition/ingredients
  if (brandUrl && brandUrl.trim()) {
    formData.append('brand_url', brandUrl.trim());
    onProgress('Uploading CSV and scraping brand website...');
  }

  onProgress('Parsing CSV and generating brand voice...');
  const result = await postForm('parse-csv', formData, 180000); // Extended timeout for brand scraping
  const products = normaliseExtractResponse(result);

  if (!products || products.length === 0) {
    throw new Error('No products found in CSV');
  }

  onProgress(`Successfully processed ${products.length} products!`);
  return products;
}

async function processSKU(searchParams: { sku?: string; barcode?: string; ean?: string; text?: string }, category: Category, onProgress: (msg: string) => void): Promise<Product[]> {
  console.log('[SKU] Starting search...');
  onProgress('Searching for products...');

  const searchQuery = searchParams.sku || searchParams.barcode || searchParams.ean || searchParams.text || '';

  const result = await postJson('search-product', { query: searchQuery.trim(), category, search_type: 'sku' });
  const products = normaliseExtractResponse(result);

  if (!products || products.length === 0) {
    throw new Error('No products found');
  }

  onProgress(`Successfully found ${products.length} products!`);
  return products;
}

async function processURL(url: string, category: Category, onProgress: (msg: string) => void): Promise<Product[]> {
  console.log('[URL] Starting scraping...');
  onProgress('Fetching website...');

  try {
    const result = await postJson('scrape-url', { url, category });
    const products = normaliseExtractResponse(result);

    if (!products || products.length === 0) {
      throw new Error('No products found at URL');
    }

    onProgress(`Successfully scraped ${products.length} products!`);
    return products;
  } catch (error: any) {
    if (error.message && error.message.includes('blocking')) {
      throw new Error('⚠️ This website blocked our scraper. Please try using CSV upload instead.');
    }
    throw error;
  }
}

// ============================================================
// EXPORT FUNCTIONS
// ============================================================

async function exportToShopify(products: Product[]): Promise<void> {
  console.log(`[Export] Exporting ${products.length} products to Shopify CSV...`);

  try {
    const response = await fetch(`${API_BASE}/export-shopify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.REACT_APP_DOCLING_API_KEY || '',
      },
      body: JSON.stringify({ products }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Export failed: ${errorText}`);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `earthfare_shopify_import_${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    console.log(`[Export] Successfully exported ${products.length} products to Shopify format`);
  } catch (error) {
    console.error('[Export] Error:', error);
    throw error;
  }
}

async function exportToBusinessCentral(products: Product[], format: 'csv' | 'excel' = 'csv'): Promise<void> {
  console.log(`[Export] Exporting ${products.length} products as ${format.toUpperCase()}...`);

  try {
    const response = await fetch(`${API_BASE}/export`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.REACT_APP_DOCLING_API_KEY || '',
      },
      body: JSON.stringify({
        products: products,
        format: format,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Export failed: ${errorText}`);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = format === 'excel'
      ? `earthfare_export_${Date.now()}.xlsx`
      : `earthfare_export_${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    console.log(`[Export] Successfully exported ${products.length} products`);
  } catch (error) {
    console.error('[Export] Error:', error);
    throw error;
  }
}

const CategorySelect: React.FC<{ id: string; value?: string; suggested?: string; onChange: (val: string) => void; }> = ({ id, value, suggested, onChange }) => (
  <div style={{ marginBottom: '0.5rem' }}>
    <label htmlFor={id} style={{ fontWeight: 600, display: 'block', marginBottom: '6px', color: COLORS.text }}>Category:</label>
    <select id={id} value={value || ''} onChange={(e) => onChange(e.target.value)} style={{ ...INPUT_BASE, cursor: 'pointer' }}>
      <option value="">-- Select Category --</option>
      {CATEGORY_OPTIONS.map((cat) => (
        <option key={cat} value={cat}>{cat} {suggested === cat ? ' ⭐' : ''}</option>
      ))}
    </select>
  </div>
);

// Helper to count CSV rows
async function countCSVRows(file: File): Promise<number> {
  const text = await file.text();
  const lines = text.split('\n').filter(line => line.trim().length > 0);
  return Math.max(0, lines.length - 1); // Subtract header row
}

const UniversalUploader: React.FC = () => {
  const [step, setStep] = useState<Step>('input');
  const [activeTab, setActiveTab] = useState<Tab>('csv');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState('');
  const [statusMsg, setStatusMsg] = useState('');
  const [editingProducts, setEditingProducts] = useState<Product[]>([]);
  const [preSelectedCategory, setPreSelectedCategory] = useState<Category | ''>('');
  const [searchSKU, setSearchSKU] = useState('');
  const [searchBarcode, setSearchBarcode] = useState('');
  const [searchEAN, setSearchEAN] = useState('');
  const [searchText, setSearchText] = useState('');
  const [isExporting, setIsExporting] = useState(false);
  const [brandUrl, setBrandUrl] = useState('');

  // Progress tracking state
  const [totalItems, setTotalItems] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [processingStartTime, setProcessingStartTime] = useState<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  // Timer effect for elapsed time during processing
  React.useEffect(() => {
    let interval: NodeJS.Timeout | null = null;
    if (step === 'processing' && processingStartTime) {
      interval = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - processingStartTime) / 1000));
      }, 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [step, processingStartTime]);

  const handleProcess = async () => {
    try {
      setStep('processing');
      setStatusMsg('Starting...');
      setElapsedTime(0);
      setProcessingStartTime(Date.now());

      let products: Product[] = [];

      switch (activeTab) {
        case 'csv':
          if (!selectedFile) throw new Error('No file selected');
          if (!preSelectedCategory) throw new Error('Please select a category');

          // Count rows for progress indicator
          const rowCount = await countCSVRows(selectedFile);
          setTotalItems(rowCount);
          setStatusMsg(`Processing ${rowCount} products...`);

          products = await processCSV(selectedFile, preSelectedCategory, brandUrl, setStatusMsg);
          break;

        case 'manual-codes':
          if (!preSelectedCategory) throw new Error('Please select a category');
          products = await processSKU({ sku: searchSKU, barcode: searchBarcode, ean: searchEAN, text: searchText }, preSelectedCategory, setStatusMsg);
          break;

        case 'website-url':
          if (!textInput.trim()) throw new Error('No URL entered');
          if (!preSelectedCategory) throw new Error('Please select a category');
          products = await processURL(textInput, preSelectedCategory, setStatusMsg);
          break;
      }

      const productsWithIds = products.map((p, idx) => ({ ...p, id: p.id || `${p.sku || 'product'}-${Date.now()}-${idx}` }));
      setEditingProducts(productsWithIds);
      setStep('complete');
      setStatusMsg(`Successfully processed ${productsWithIds.length} product${productsWithIds.length === 1 ? '' : 's'}!`);
    } catch (err) {
      console.error('Processing error:', err);
      setStep('input');
      setStatusMsg('');
      alert(`Error: ${toMessage(err)}`);
    }
  };

  // Export handlers
  const handleExportShopify = async () => {
    setIsExporting(true);
    try {
      await exportToShopify(editingProducts);
      setStatusMsg('Shopify CSV exported successfully!');
    } catch (error) {
      console.error('Shopify export failed:', error);
      alert(`Shopify export failed: ${toMessage(error)}`);
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportCSV = async () => {
    setIsExporting(true);
    try {
      await exportToBusinessCentral(editingProducts, 'csv');
      setStatusMsg('CSV exported successfully!');
    } catch (error) {
      console.error('CSV export failed:', error);
      alert(`CSV export failed: ${toMessage(error)}`);
    } finally {
      setIsExporting(false);
    }
  };

  const handleExportExcel = async () => {
    setIsExporting(true);
    try {
      await exportToBusinessCentral(editingProducts, 'excel');
      setStatusMsg('Excel exported successfully!');
    } catch (error) {
      console.error('Excel export failed:', error);
      alert(`Excel export failed: ${toMessage(error)}`);
    } finally {
      setIsExporting(false);
    }
  };

  const handleReset = () => {
    setStep('input');
    setSelectedFile(null);
    setTextInput('');
    setStatusMsg('');
    setEditingProducts([]);
    setPreSelectedCategory('');
    setSearchSKU('');
    setSearchBarcode('');
    setSearchEAN('');
    setSearchText('');
    setBrandUrl('');
    setTotalItems(0);
    setElapsedTime(0);
    setProcessingStartTime(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const updateProductName = (id: string, name: string) => {
    setEditingProducts(prev => prev.map(p => (p.id === id ? { ...p, name } : p)));
  };

  const updateProductSKU = (id: string, sku: string) => {
    setEditingProducts(prev => prev.map(p => (p.id === id ? { ...p, sku } : p)));
  };

  const updateProductBarcode = (id: string, barcode: string) => {
    setEditingProducts(prev => prev.map(p => (p.id === id ? { ...p, barcode } : p)));
  };

  const updateProductCategory = (id: string, category: string) => {
    setEditingProducts(prev => prev.map(p => (p.id === id ? { ...p, category } : p)));
  };

  const updateProductDescription = (id: string, field: keyof Product['descriptions'], value: string) => {
    setEditingProducts(prev =>
      prev.map(p => p.id === id ? { ...p, descriptions: { ...p.descriptions, [field]: value } as Product['descriptions'] } : p)
    );
  };

  const regenerateProduct = async (id: string) => {
    const product = editingProducts.find(p => p.id === id);
    if (!product || !product.category) {
      alert('Please select a category first');
      return;
    }

    try {
      setStatusMsg(`Regenerating product ${product.name || product.sku}...`);

      const bv = await postJson('generate-brand-voice', {
        products: [product],
        category: product.category
      }, 120000);

      const voiced = Array.isArray(bv?.products) ? bv.products[0] : null;

      if (voiced) {
        setEditingProducts(prev =>
          prev.map(p => p.id === id ? { ...voiced, id } : p)
        );
        setStatusMsg('Product regenerated successfully!');
        setTimeout(() => setStatusMsg(''), 3000);
      }
    } catch (err) {
      alert(`Regeneration failed: ${toMessage(err)}`);
    }
  };

  // Only CSV, Search Code, and Website URL tabs
  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'csv', label: 'CSV Upload', icon: '📊' },
    { key: 'manual-codes', label: 'Search Code', icon: '🔍' },
    { key: 'website-url', label: 'Website URL', icon: '🌐' },
  ];

  const isFileTab = activeTab === 'csv';

  const canProcess = (() => {
    if (activeTab === 'csv') return !!selectedFile && !!preSelectedCategory;
    if (activeTab === 'manual-codes') return !!(searchSKU.trim() || searchBarcode.trim() || searchEAN.trim() || searchText.trim()) && !!preSelectedCategory;
    if (activeTab === 'website-url') return !!textInput.trim() && !!preSelectedCategory;
    return false;
  })();

  // Render product editor (used in complete step)
  const renderProductEditor = () => (
    <>
      {/* Export Buttons */}
      <div style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <button
          onClick={handleExportShopify}
          disabled={!editingProducts.length || isExporting}
          style={{
            background: COLORS.primary,
            color: 'white',
            border: 'none',
            padding: '14px 24px',
            borderRadius: '8px',
            cursor: editingProducts.length && !isExporting ? 'pointer' : 'not-allowed',
            fontWeight: 600,
            fontSize: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
            transition: 'all 0.2s ease',
          }}
        >
          🛒 Export to Shopify
        </button>
        <button
          onClick={handleExportCSV}
          disabled={!editingProducts.length || isExporting}
          style={{
            background: COLORS.primaryLight,
            color: 'white',
            border: 'none',
            padding: '14px 24px',
            borderRadius: '8px',
            cursor: editingProducts.length && !isExporting ? 'pointer' : 'not-allowed',
            fontWeight: 600,
            fontSize: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}
        >
          📥 Export CSV
        </button>
        <button
          onClick={handleExportExcel}
          disabled={!editingProducts.length || isExporting}
          style={{
            background: COLORS.secondary,
            color: COLORS.primaryDark,
            border: 'none',
            padding: '14px 24px',
            borderRadius: '8px',
            cursor: editingProducts.length && !isExporting ? 'pointer' : 'not-allowed',
            fontWeight: 600,
            fontSize: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}
        >
          📊 Export Excel
        </button>
        <button
          onClick={handleReset}
          style={{
            background: '#e8ebe6',
            color: COLORS.text,
            border: 'none',
            padding: '14px 24px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '1rem',
          }}
        >
          🔄 Start Over
        </button>
        {isExporting && (
          <span style={{ color: COLORS.textLight, fontStyle: 'italic' }}>Exporting...</span>
        )}
      </div>

      {/* Status Message */}
      {statusMsg && (
        <div style={{ color: COLORS.success, marginBottom: '1rem', fontSize: '1.1rem', fontWeight: 500 }}>
          ✓ {statusMsg}
        </div>
      )}

      {/* Products Count */}
      <div style={{ marginBottom: '1rem', padding: '12px 16px', background: '#e8f5e9', borderRadius: '8px', display: 'inline-block', border: `1px solid ${COLORS.secondary}` }}>
        <strong style={{ color: COLORS.primary }}>{editingProducts.length}</strong> product{editingProducts.length === 1 ? '' : 's'} ready for export
      </div>

      {/* Product Cards */}
      {editingProducts.map((product, idx) => (
        <div key={product.id} style={{ border: BORDER_THIN, borderRadius: '12px', padding: '1.5rem', marginBottom: '1.5rem', background: COLORS.cardBg, boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
          <h3 style={{ marginTop: 0, marginBottom: '1rem', color: COLORS.primary, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Product {idx + 1}</span>
            <span style={{ fontSize: '0.85rem', color: COLORS.textLight, fontWeight: 400 }}>
              {product.source && `Source: ${product.source}`}
            </span>
          </h3>
          <div style={{ display: 'grid', gap: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Name:</label>
                <input type="text" value={product.name} onChange={(e) => updateProductName(product.id, e.target.value)} style={{ ...INPUT_BASE }} />
              </div>
              <div>
                <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>SKU:</label>
                <input type="text" value={product.sku} onChange={(e) => updateProductSKU(product.id, e.target.value)} style={{ ...INPUT_BASE }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Barcode/EAN:</label>
                <input type="text" value={product.barcode || ''} onChange={(e) => updateProductBarcode(product.id, e.target.value)} style={{ ...INPUT_BASE }} placeholder="Enter barcode or EAN" />
              </div>
              <div>
                <CategorySelect id={`category-${product.id}`} value={product.category} onChange={(val) => updateProductCategory(product.id, val)} />
              </div>
            </div>

            {/* Dietary info display - check both dietary_preferences and dietary_info */}
            {((product.dietary_preferences && product.dietary_preferences.length > 0) ||
              (product.dietary_info && product.dietary_info.length > 0)) && (
              <div>
                <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Dietary:</label>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {[...(product.dietary_preferences || []), ...(product.dietary_info || [])]
                    .filter((v, i, a) => a.indexOf(v) === i) // Remove duplicates
                    .map((diet, i) => (
                    <span key={i} style={{
                      background: COLORS.secondary,
                      color: COLORS.primaryDark,
                      padding: '4px 12px',
                      borderRadius: '16px',
                      fontSize: '0.85rem',
                      fontWeight: 500
                    }}>
                      {diet}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Data Sources - Show where data came from */}
            {(product.data_sources && product.data_sources.length > 0) || product.data_source_url ? (
              <div style={{ background: '#e3f2fd', padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid #90caf9', marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '0.85rem', color: '#1565c0', fontWeight: 600 }}>📍 Data Sources:</span>
                  {product.data_sources?.map((source, i) => (
                    <span key={i} style={{
                      background: '#bbdefb',
                      color: '#0d47a1',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '0.8rem'
                    }}>
                      {source}
                    </span>
                  ))}
                  {product.data_source_url && (
                    <a
                      href={product.data_source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: '0.8rem',
                        color: '#1565c0',
                        textDecoration: 'underline'
                      }}
                    >
                      Verify Source ↗
                    </a>
                  )}
                </div>
              </div>
            ) : null}

            {/* Ingredients and Nutrition - Two Column Layout */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
              {/* Ingredients */}
              <div style={{ background: COLORS.background, padding: '1rem', borderRadius: '8px', border: BORDER_THIN }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <label style={{ fontWeight: 600, color: COLORS.primary, fontSize: '1rem' }}>
                    🥗 Ingredients
                  </label>
                  {product.ingredients_source && (
                    <span style={{ fontSize: '0.7rem', color: COLORS.textLight, background: '#e8f5e9', padding: '2px 6px', borderRadius: '4px' }}>
                      via {product.ingredients_source}
                    </span>
                  )}
                </div>
                {product.ingredients ? (
                  <p style={{ margin: 0, color: COLORS.text, lineHeight: '1.5', fontSize: '0.9rem' }}>
                    {product.ingredients}
                  </p>
                ) : (
                  <p style={{ margin: 0, color: COLORS.textLight, fontStyle: 'italic', fontSize: '0.9rem' }}>
                    No ingredients data available
                  </p>
                )}
              </div>

              {/* Nutrition Table */}
              <div style={{ background: COLORS.background, padding: '1rem', borderRadius: '8px', border: BORDER_THIN }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <label style={{ fontWeight: 600, color: COLORS.primary, fontSize: '1rem' }}>
                    📊 Nutrition (per 100g)
                  </label>
                  {product.nutrition_source && (
                    <span style={{ fontSize: '0.7rem', color: COLORS.textLight, background: '#e8f5e9', padding: '2px 6px', borderRadius: '4px' }}>
                      via {product.nutrition_source}
                    </span>
                  )}
                </div>
                {product.nutrition && Object.keys(product.nutrition).length > 0 ? (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                    <tbody>
                      {product.nutrition.energy_kcal && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 0', color: COLORS.text }}>Energy</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: 500 }}>{product.nutrition.energy_kcal} kcal</td>
                        </tr>
                      )}
                      {product.nutrition.fat && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 0', color: COLORS.text }}>Fat</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: 500 }}>{product.nutrition.fat}g</td>
                        </tr>
                      )}
                      {product.nutrition.saturates && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 0', paddingLeft: '12px', color: COLORS.textLight, fontSize: '0.8rem' }}>of which saturates</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontSize: '0.8rem' }}>{product.nutrition.saturates}g</td>
                        </tr>
                      )}
                      {product.nutrition.carbohydrates && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 0', color: COLORS.text }}>Carbohydrates</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: 500 }}>{product.nutrition.carbohydrates}g</td>
                        </tr>
                      )}
                      {product.nutrition.sugars && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 0', paddingLeft: '12px', color: COLORS.textLight, fontSize: '0.8rem' }}>of which sugars</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontSize: '0.8rem' }}>{product.nutrition.sugars}g</td>
                        </tr>
                      )}
                      {product.nutrition.fibre && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 0', color: COLORS.text }}>Fibre</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: 500 }}>{product.nutrition.fibre}g</td>
                        </tr>
                      )}
                      {product.nutrition.protein && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                          <td style={{ padding: '6px 0', color: COLORS.text }}>Protein</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: 500 }}>{product.nutrition.protein}g</td>
                        </tr>
                      )}
                      {product.nutrition.salt && (
                        <tr>
                          <td style={{ padding: '6px 0', color: COLORS.text }}>Salt</td>
                          <td style={{ padding: '6px 0', textAlign: 'right', fontWeight: 500 }}>{product.nutrition.salt}g</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                ) : (
                  <p style={{ margin: 0, color: COLORS.textLight, fontStyle: 'italic', fontSize: '0.9rem' }}>
                    No nutrition data available
                  </p>
                )}
              </div>
            </div>

            {/* Allergens */}
            {product.allergens && (
              <div style={{ background: '#fff8e1', padding: '1rem', borderRadius: '8px', border: `1px solid ${COLORS.warning}` }}>
                <label style={{ fontWeight: 600, display: 'block', marginBottom: '8px', color: '#e65100', fontSize: '1rem' }}>
                  ⚠️ Allergen Information
                </label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {product.allergens.contains && product.allergens.contains.length > 0 && (
                    <div>
                      <strong style={{ color: COLORS.error, fontSize: '0.85rem' }}>Contains: </strong>
                      <span style={{ fontSize: '0.85rem' }}>{product.allergens.contains.join(', ')}</span>
                    </div>
                  )}
                  {product.allergens.may_contain && product.allergens.may_contain.length > 0 && (
                    <div>
                      <strong style={{ color: COLORS.warning, fontSize: '0.85rem' }}>May Contain: </strong>
                      <span style={{ fontSize: '0.85rem' }}>{product.allergens.may_contain.join(', ')}</span>
                    </div>
                  )}
                  {product.allergens.free_from && product.allergens.free_from.length > 0 && (
                    <div>
                      <strong style={{ color: COLORS.success, fontSize: '0.85rem' }}>Free From: </strong>
                      <span style={{ fontSize: '0.85rem' }}>{product.allergens.free_from.join(', ')}</span>
                    </div>
                  )}
                  {(!product.allergens.contains || product.allergens.contains.length === 0) &&
                   (!product.allergens.may_contain || product.allergens.may_contain.length === 0) &&
                   (!product.allergens.free_from || product.allergens.free_from.length === 0) && (
                    <p style={{ margin: 0, color: COLORS.textLight, fontStyle: 'italic', fontSize: '0.85rem' }}>
                      No allergen data available
                    </p>
                  )}
                </div>
              </div>
            )}

            <div>
              <button
                onClick={() => regenerateProduct(product.id)}
                style={{
                  padding: '10px 18px',
                  background: COLORS.primary,
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem'
                }}
              >
                🔄 Regenerate with Category
              </button>
            </div>
            <div>
              <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Short Description:</label>
              <textarea value={product.descriptions?.shortDescription || ''} onChange={(e) => updateProductDescription(product.id, 'shortDescription', e.target.value)} rows={3} style={{ ...INPUT_BASE, resize: 'vertical' }} />
            </div>
            <div>
              <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Meta Description:</label>
              <textarea value={product.descriptions?.metaDescription || ''} onChange={(e) => updateProductDescription(product.id, 'metaDescription', e.target.value)} rows={2} style={{ ...INPUT_BASE, resize: 'vertical' }} />
              <span style={{ fontSize: '0.8rem', color: COLORS.textLight }}>
                {(product.descriptions?.metaDescription || '').length}/160 characters
              </span>
            </div>
            <div>
              <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Long Description:</label>
              <textarea value={product.descriptions?.longDescription || ''} onChange={(e) => updateProductDescription(product.id, 'longDescription', e.target.value)} rows={6} style={{ ...INPUT_BASE, resize: 'vertical' }} />
            </div>
          </div>
        </div>
      ))}
    </>
  );

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '2rem', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* EarthFare Header */}
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '12px',
          marginBottom: '1rem',
          background: COLORS.primary,
          padding: '16px 32px',
          borderRadius: '12px',
        }}>
          <span style={{ fontSize: '2.5rem' }}>🌿</span>
          <div style={{ textAlign: 'left' }}>
            <h1 style={{ fontSize: '2rem', margin: 0, color: 'white', fontWeight: 700 }}>EarthFare</h1>
            <p style={{ fontSize: '0.9rem', color: COLORS.secondary, margin: 0, fontWeight: 500 }}>Product Automation</p>
          </div>
        </div>
        <p style={{ fontSize: '1.1rem', color: COLORS.textLight, maxWidth: '600px', margin: '1rem auto 0' }}>
          Natural, Local, Organic, Ethical, Ecological. Upload your product data and generate professional descriptions with our brand voice.
        </p>
      </div>

      {/* INPUT STEP */}
      {step === 'input' && (
        <>
          <div style={{ display: 'flex', gap: '10px', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => {
                  setActiveTab(tab.key);
                  setSelectedFile(null);
                  setTextInput('');
                  if (activeTab === 'manual-codes') {
                    setSearchSKU('');
                    setSearchBarcode('');
                    setSearchEAN('');
                    setSearchText('');
                  }
                  setPreSelectedCategory('');
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }}
                style={{
                  padding: '12px 20px',
                  border: activeTab === tab.key ? `2px solid ${COLORS.primary}` : BORDER_THIN,
                  background: activeTab === tab.key ? '#e8f5e9' : 'white',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  fontWeight: activeTab === tab.key ? 600 : 400,
                  color: activeTab === tab.key ? COLORS.primary : COLORS.textLight,
                  transition: 'all 0.2s ease',
                  fontSize: '1rem',
                }}
              >
                {tab.icon} {tab.label}
              </button>
            ))}
          </div>

          <CategorySelect id="pre-category" value={preSelectedCategory} onChange={(val) => setPreSelectedCategory(val as Category | '')} />

          <div style={{ marginTop: '1.5rem' }}>
            {isFileTab && (
              <>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleFileChange}
                  style={{ display: 'none' }}
                  id="file-upload"
                />
                <label htmlFor="file-upload" style={{
                  display: 'block',
                  padding: '3rem',
                  border: `2px dashed ${selectedFile ? COLORS.primary : COLORS.border}`,
                  borderRadius: '12px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  background: selectedFile ? '#e8f5e9' : COLORS.background,
                  transition: 'all 0.2s ease'
                }}>
                  <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>📤</div>
                  <p style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: COLORS.text, fontWeight: 500 }}>
                    {selectedFile ? `Selected: ${selectedFile.name}` : 'Click to upload or drag and drop'}
                  </p>
                  <p style={{ fontSize: '0.9rem', color: COLORS.textLight }}>
                    CSV files with product data
                  </p>
                </label>

                {/* Brand URL - Optional field for scraping manufacturer website */}
                <div style={{ marginTop: '1.5rem' }}>
                  <label htmlFor="brand-url" style={{
                    fontWeight: 600,
                    display: 'block',
                    marginBottom: '6px',
                    color: COLORS.text
                  }}>
                    Brand Website URL <span style={{ fontWeight: 400, color: COLORS.textLight }}>(optional)</span>:
                  </label>
                  <input
                    id="brand-url"
                    type="url"
                    value={brandUrl}
                    onChange={(e) => setBrandUrl(e.target.value)}
                    placeholder="e.g., https://www.brandname.com/products"
                    style={{ ...INPUT_BASE }}
                  />
                  <p style={{ fontSize: '0.85rem', color: COLORS.textLight, marginTop: '0.5rem', lineHeight: '1.4' }}>
                    💡 <strong>Tip:</strong> Add a manufacturer website URL to pull additional data like nutrition and ingredients
                    when OpenFoodFacts doesn't have the product. Useful for supplements and specialist products.
                  </p>
                </div>
              </>
            )}

            {activeTab === 'manual-codes' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <p style={{ fontSize: '0.95rem', color: COLORS.textLight, marginBottom: '0.5rem' }}>Enter at least one search criterion to find products:</p>
                <div>
                  <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>SKU:</label>
                  <input type="text" value={searchSKU} onChange={(e) => setSearchSKU(e.target.value)} placeholder="e.g., SKU123" style={{ ...INPUT_BASE }} />
                </div>
                <div>
                  <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Barcode:</label>
                  <input type="text" value={searchBarcode} onChange={(e) => setSearchBarcode(e.target.value)} placeholder="e.g., 1234567890123" style={{ ...INPUT_BASE }} />
                </div>
                <div>
                  <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>EAN:</label>
                  <input type="text" value={searchEAN} onChange={(e) => setSearchEAN(e.target.value)} placeholder="e.g., 5012345678900" style={{ ...INPUT_BASE }} />
                </div>
                <div>
                  <label style={{ fontWeight: 600, display: 'block', marginBottom: '4px', color: COLORS.text }}>Text Search:</label>
                  <input type="text" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="e.g., product name or description" style={{ ...INPUT_BASE }} />
                </div>
              </div>
            )}

            {activeTab === 'website-url' && (
              <>
                <textarea
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder="Enter supplier product URL&#10;Example: https://www.suma.coop/product/12345"
                  rows={4}
                  style={{ ...INPUT_BASE, resize: 'vertical' }}
                />
                <p style={{ fontSize: '0.85rem', color: COLORS.warning, marginTop: '0.5rem', lineHeight: '1.4' }}>
                  ⚠️ <strong>Note:</strong> Some websites block automated scraping for security.
                  If scraping fails, please use CSV Upload instead.
                </p>
              </>
            )}
          </div>

          <button
            onClick={handleProcess}
            disabled={!canProcess}
            style={{
              marginTop: '1.5rem',
              padding: '14px 36px',
              border: 'none',
              borderRadius: '8px',
              background: canProcess ? COLORS.primary : '#bdc3c7',
              color: '#fff',
              cursor: canProcess ? 'pointer' : 'not-allowed',
              fontSize: '1.1rem',
              fontWeight: 600,
              transition: 'all 0.2s ease',
              boxShadow: canProcess ? '0 2px 8px rgba(45, 90, 39, 0.3)' : 'none',
            }}
          >
            Process Products
          </button>
        </>
      )}

      {/* PROCESSING STEP - Show loading */}
      {step === 'processing' && (
        <div style={{ textAlign: 'center', padding: '3rem' }}>
          {/* Animated spinner */}
          <div style={{
            width: '80px',
            height: '80px',
            margin: '0 auto 1.5rem',
            position: 'relative',
          }}>
            <div style={{
              position: 'absolute',
              width: '100%',
              height: '100%',
              border: '4px solid ' + COLORS.border,
              borderTopColor: COLORS.primary,
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
            }} />
            <div style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              fontSize: '1.8rem',
            }}>🌿</div>
          </div>

          {/* Status message */}
          <p style={{ fontSize: '1.3rem', color: COLORS.text, fontWeight: 600, marginBottom: '0.5rem' }}>
            {statusMsg || 'Processing...'}
          </p>

          {/* Item count */}
          {totalItems > 0 && (
            <p style={{ fontSize: '1.1rem', color: COLORS.primary, fontWeight: 500, marginBottom: '0.5rem' }}>
              {totalItems} product{totalItems !== 1 ? 's' : ''} in queue
            </p>
          )}

          {/* Elapsed time */}
          <p style={{ fontSize: '0.95rem', color: COLORS.textLight, marginBottom: '1.5rem' }}>
            ⏱️ Elapsed: {Math.floor(elapsedTime / 60)}:{(elapsedTime % 60).toString().padStart(2, '0')}
          </p>

          {/* Progress bar */}
          <div style={{
            width: '280px',
            height: '8px',
            background: COLORS.border,
            borderRadius: '4px',
            margin: '0 auto 1rem',
            overflow: 'hidden',
            position: 'relative',
          }}>
            <div style={{
              position: 'absolute',
              width: '40%',
              height: '100%',
              background: `linear-gradient(90deg, ${COLORS.primary}, ${COLORS.primaryLight}, ${COLORS.primary})`,
              borderRadius: '4px',
              animation: 'progressSlide 1.5s ease-in-out infinite',
            }} />
          </div>

          {/* Helpful info */}
          <p style={{ fontSize: '0.85rem', color: COLORS.textLight, marginTop: '1rem' }}>
            {totalItems > 20
              ? '⚡ Large file detected - this may take 2-5 minutes'
              : totalItems > 0
                ? '✨ Enriching products with nutrition data...'
                : 'Connecting to servers...'}
          </p>

          {/* Add keyframe animations */}
          <style>{`
            @keyframes spin {
              to { transform: rotate(360deg); }
            }
            @keyframes progressSlide {
              0% { left: -40%; }
              100% { left: 100%; }
            }
          `}</style>
        </div>
      )}

      {/* COMPLETE STEP - Show products and export options */}
      {step === 'complete' && renderProductEditor()}

      {/* Footer */}
      <div style={{
        marginTop: '4rem',
        textAlign: 'center',
        padding: '1.5rem',
        borderTop: BORDER_THIN,
        color: COLORS.textLight,
        fontSize: '0.9rem'
      }}>
        <p style={{ margin: 0 }}>
          🌿 EarthFare Eco Supermarket • Glastonbury, Somerset
        </p>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.8rem' }}>
          Natural, Local, Organic, Ethical, Ecological
        </p>
      </div>
    </div>
  );
};

export default UniversalUploader;
