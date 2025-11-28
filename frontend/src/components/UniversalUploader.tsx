// src/components/UniversalUploader.tsx
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
  };
  images?: string[];
  price?: string | null;
};

type Step = 'input' | 'processing' | 'complete';
type Tab = 'pdf-catalogue' | 'csv' | 'product-image' | 'manual-codes' | 'website-url' | 'free-text';

type Category =
  | 'Clothing'
  | 'Electricals'
  | 'Bakeware, Cookware'
  | 'Dining, Drink, Living'
  | 'Knives, Cutlery'
  | 'Food Prep & Tools';

const CATEGORY_OPTIONS: readonly Category[] = [
  'Clothing',
  'Electricals',
  'Bakeware, Cookware',
  'Dining, Drink, Living',
  'Knives, Cutlery',
  'Food Prep & Tools',
] as const;

const API_BASE = 
  process.env.REACT_APP_API_BASE ||
  (process.env.REACT_APP_BACKEND_URL ? process.env.REACT_APP_BACKEND_URL + '/api' : '') ||
  'https://docling-service-u53318.vm.elestio.app/api';

console.log('FastAPI Backend URL:', API_BASE);

const BORDER_THIN = '1px solid #ddd';
const INPUT_BASE = {
  width: '100%',
  padding: '10px',
  border: BORDER_THIN,
  borderRadius: '6px',
  fontSize: '1rem',
} as const;

const toMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

const stripHtml = (html: string) => (html || '').replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();

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

async function processPDF(file: File, category: Category, onProgress: (msg: string) => void): Promise<Product[]> {
  console.log('[PDF] Starting...');
  if (!file) throw new Error('No file selected');
  if (!category) throw new Error('Please select a category');

  onProgress('Uploading PDF (this may take 3-7 minutes)...');

  const formData = new FormData();
  formData.append('file', file, file.name);

  const extractJson = await postForm('extract-pdf-products', formData, 600000);
  const products = normaliseExtractResponse(extractJson);
  
  if (!products || products.length === 0) {
    throw new Error('No products detected in the PDF.');
  }

  const productsWithCategory = products.map(p => ({ ...p, category }));
  onProgress(`Generating brand voice for ${products.length} products...`);

  const bv = await postJson('generate-brand-voice', { products: productsWithCategory, category }, 120000);
  const voiced = Array.isArray(bv?.products) ? bv.products : [];

  if (voiced.length === 0) {
    console.warn('[PDF] No brand voice generated');
    onProgress(`Processed ${products.length} products (brand voice unavailable)`);
    return productsWithCategory;
  }

  onProgress(`Successfully processed ${voiced.length} products!`);
  return voiced;
}

async function processCSV(file: File, category: Category, onProgress: (msg: string) => void): Promise<Product[]> {
  console.log('[CSV] Starting...');
  onProgress('Uploading CSV...');

  const formData = new FormData();
  formData.append('file', file, file.name);
  formData.append('category', category);

  onProgress('Parsing CSV and generating brand voice...');
  const result = await postForm('parse-csv', formData, 120000);
  const products = normaliseExtractResponse(result);

  if (!products || products.length === 0) {
    throw new Error('No products found in CSV');
  }

  onProgress(`Successfully processed ${products.length} products!`);
  return products;
}

async function processImage(file: File, category: Category, additionalText: string, onProgress: (msg: string) => void): Promise<Product[]> {
  console.log('[Image] Starting AI Vision...');
  onProgress('Uploading image...');

  const formData = new FormData();
  formData.append('file', file, file.name);
  formData.append('category', category);
  formData.append('additional_text', additionalText);

  onProgress('Analyzing image with AI...');
  const result = await postForm('parse-image', formData, 120000);
  const products = normaliseExtractResponse(result);

  if (!products || products.length === 0) {
    throw new Error('No product info detected in image.');
  }

  onProgress(`Successfully extracted ${products.length} products!`);
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
      throw new Error('⚠️ This website blocked our scraper.\n\nPlease:\n1. Copy the product details from the website\n2. Switch to the "Free Text" tab\n3. Paste the information there');
    }
    throw error;
  }
}

async function processFreeText(text: string, category: Category, onProgress: (msg: string) => void): Promise<Product[]> {
  console.log('[FreeText] Starting...');
  onProgress('Processing text...');

  const result = await postJson('process-text', { text, category });
  const products = normaliseExtractResponse(result);

  if (!products || products.length === 0) {
    throw new Error('Failed to process text');
  }

  onProgress('Successfully processed!');
  return products;
}

// ============================================================
// EXPORT FUNCTIONS - Business Central format via API
// ============================================================

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

    // Get the blob from response
    const blob = await response.blob();
    
    // Create download link
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = format === 'excel' 
      ? `products_export_${Date.now()}.xlsx` 
      : `products_export_${Date.now()}.csv`;
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

// Legacy client-side export (fallback if API fails)
function exportToCSVLegacy(products: Product[]) {
  const headers = ['SKU', 'Barcode', 'Description', 'Net Weight (KG)', 'Short Description', 'Long Description', 'IMAGE', 'IMAGE 1', 'IMAGE 2', 'IMAGE 3', 'IMAGE 4', 'IMAGE 5'];
  const rows = products.map(p => {
    const images = p.images || [];
    const sku = p.sku || '';
    const name = (p.name || '').replace(/ /g, '-').replace(/[^\w-]/g, '').substring(0, 50);
    
    return [
      sku,
      p.barcode || '',
      p.name || '',
      p.specifications?.weight || '',
      `<p>${(p.descriptions?.shortDescription || '').split('\n').filter(l => l.trim()).join(',<br>')}</p>`,
      p.descriptions?.longDescription || '',
      images[0] || `products\\${sku}-${name}.jpg`,
      images[1] || `products\\${sku}-${name}-1.jpg`,
      images[2] || `products\\${sku}-${name}-2.jpg`,
      images[3] || `products\\${sku}-${name}-3.jpg`,
      images[4] || `products\\${sku}-${name}-4.jpg`,
      images[5] || `products\\${sku}-${name}-5.jpg`,
    ];
  });

  const csvContent = '\uFEFF' + [
    headers.join(','),
    ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')),
  ].join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `products-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

const CategorySelect: React.FC<{ id: string; value?: string; suggested?: string; onChange: (val: string) => void; }> = ({ id, value, suggested, onChange }) => (
  <div style={{ marginBottom: '0.5rem' }}>
    <label htmlFor={id} style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Category:</label>
    <select id={id} value={value || ''} onChange={(e) => onChange(e.target.value)} style={{ ...INPUT_BASE }}>
      <option value="">-- Select Category --</option>
      {CATEGORY_OPTIONS.map((cat) => (
        <option key={cat} value={cat}>{cat} {suggested === cat ? ' ⭐' : ''}</option>
      ))}
    </select>
  </div>
);

const UniversalUploader: React.FC = () => {
  const [step, setStep] = useState<Step>('input');
  const [activeTab, setActiveTab] = useState<Tab>('pdf-catalogue');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState('');
  const [imageAdditionalText, setImageAdditionalText] = useState('');
  const [statusMsg, setStatusMsg] = useState('');
  const [editingProducts, setEditingProducts] = useState<Product[]>([]);
  const [preSelectedCategory, setPreSelectedCategory] = useState<Category | ''>('');
  const [searchSKU, setSearchSKU] = useState('');
  const [searchBarcode, setSearchBarcode] = useState('');
  const [searchEAN, setSearchEAN] = useState('');
  const [searchText, setSearchText] = useState('');
  const [isExporting, setIsExporting] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  };

  const handleProcess = async () => {
    try {
      setStep('processing');
      setStatusMsg('Starting...');

      let products: Product[] = [];

      switch (activeTab) {
        case 'pdf-catalogue':
          if (!selectedFile) throw new Error('No file selected');
          if (!preSelectedCategory) throw new Error('Please select a category');
          products = await processPDF(selectedFile, preSelectedCategory as Category, setStatusMsg);
          break;

        case 'csv':
          if (!selectedFile) throw new Error('No file selected');
          if (!preSelectedCategory) throw new Error('Please select a category');
          products = await processCSV(selectedFile, preSelectedCategory, setStatusMsg);
          break;

        case 'product-image':
          if (!selectedFile) throw new Error('No file selected');
          if (!preSelectedCategory) throw new Error('Please select a category');
          products = await processImage(selectedFile, preSelectedCategory, imageAdditionalText, setStatusMsg);
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

        case 'free-text':
          if (!textInput.trim()) throw new Error('No text entered');
          if (!preSelectedCategory) throw new Error('Please select a category');
          products = await processFreeText(textInput, preSelectedCategory, setStatusMsg);
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
  const handleExportCSV = async () => {
    setIsExporting(true);
    try {
      await exportToBusinessCentral(editingProducts, 'csv');
      setStatusMsg('CSV exported successfully!');
    } catch (error) {
      console.warn('API export failed, using legacy export:', error);
      exportToCSVLegacy(editingProducts);
      setStatusMsg('CSV exported (legacy mode)');
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
    setImageAdditionalText('');
    setStatusMsg('');
    setEditingProducts([]);
    setPreSelectedCategory('');
    setSearchSKU('');
    setSearchBarcode('');
    setSearchEAN('');
    setSearchText('');
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
  
  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: 'pdf-catalogue', label: 'PDF Catalogue', icon: '📄' },
    { key: 'csv', label: 'CSV Upload', icon: '📊' },
    { key: 'product-image', label: 'Product Image', icon: '📸' },
    { key: 'manual-codes', label: 'Search Code', icon: '🔍' },
    { key: 'website-url', label: 'Website URL', icon: '🌐' },
    { key: 'free-text', label: 'Free Text', icon: '📝' },
  ];

  const isFileTab = ['pdf-catalogue', 'csv', 'product-image'].includes(activeTab);

  const canProcess = (() => {
    if (activeTab === 'pdf-catalogue' || activeTab === 'product-image') return !!selectedFile && !!preSelectedCategory;
    if (activeTab === 'csv') return !!selectedFile && !!preSelectedCategory;
    if (activeTab === 'manual-codes') return !!(searchSKU.trim() || searchBarcode.trim() || searchEAN.trim() || searchText.trim()) && !!preSelectedCategory;
    if (activeTab === 'website-url') return !!textInput.trim() && !!preSelectedCategory;
    if (activeTab === 'free-text') return !!textInput.trim() && !!preSelectedCategory;
    return false;
  })();

  // Render product editor (used in both processing and complete steps)
  const renderProductEditor = () => (
    <>
      {/* Export Buttons */}
      <div style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        <button 
          onClick={handleExportCSV} 
          disabled={!editingProducts.length || isExporting} 
          style={{ 
            background: '#27ae60', 
            color: 'white', 
            border: 'none', 
            padding: '12px 20px', 
            borderRadius: '6px', 
            cursor: editingProducts.length && !isExporting ? 'pointer' : 'not-allowed', 
            fontWeight: 600,
            fontSize: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          📥 Export CSV (Business Central)
        </button>
        <button 
          onClick={handleExportExcel} 
          disabled={!editingProducts.length || isExporting} 
          style={{ 
            background: '#2980b9', 
            color: 'white', 
            border: 'none', 
            padding: '12px 20px', 
            borderRadius: '6px', 
            cursor: editingProducts.length && !isExporting ? 'pointer' : 'not-allowed', 
            fontWeight: 600,
            fontSize: '1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          📊 Export Excel
        </button>
        <button 
          onClick={handleReset} 
          style={{ 
            background: '#e0e0e0', 
            color: '#2c3e50', 
            border: 'none', 
            padding: '12px 20px', 
            borderRadius: '6px', 
            cursor: 'pointer', 
            fontWeight: 600,
            fontSize: '1rem',
          }}
        >
          🔄 Start Over
        </button>
        {isExporting && (
          <span style={{ color: '#7f8c8d', fontStyle: 'italic' }}>Exporting...</span>
        )}
      </div>

      {/* Status Message */}
      {statusMsg && (
        <div style={{ color: '#27ae60', marginBottom: '1rem', fontSize: '1.1rem', fontWeight: 500 }}>
          ✓ {statusMsg}
        </div>
      )}

      {/* Products Count */}
      <div style={{ marginBottom: '1rem', padding: '12px 16px', background: '#e8f5e9', borderRadius: '6px', display: 'inline-block' }}>
        <strong>{editingProducts.length}</strong> product{editingProducts.length === 1 ? '' : 's'} ready for export
      </div>

      {/* Product Cards */}
      {editingProducts.map((product, idx) => (
        <div key={product.id} style={{ border: BORDER_THIN, borderRadius: '8px', padding: '1.5rem', marginBottom: '1.5rem', background: '#f9f9f9' }}>
          <h3 style={{ marginTop: 0, marginBottom: '1rem', color: '#333', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Product {idx + 1}</span>
            <span style={{ fontSize: '0.85rem', color: '#7f8c8d', fontWeight: 400 }}>
              {product.source && `Source: ${product.source}`}
            </span>
          </h3>
          <div style={{ display: 'grid', gap: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Name:</label>
                <input type="text" value={product.name} onChange={(e) => updateProductName(product.id, e.target.value)} style={{ ...INPUT_BASE }} />
              </div>
              <div>
                <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>SKU:</label>
                <input type="text" value={product.sku} onChange={(e) => updateProductSKU(product.id, e.target.value)} style={{ ...INPUT_BASE }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div>
                <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Barcode/EAN:</label>
                <input type="text" value={product.barcode || ''} onChange={(e) => updateProductBarcode(product.id, e.target.value)} style={{ ...INPUT_BASE }} placeholder="Enter barcode or EAN" />
              </div>
              <div>
                <CategorySelect id={`category-${product.id}`} value={product.category} onChange={(val) => updateProductCategory(product.id, val)} />
              </div>
            </div>
            <div>
              <button 
                onClick={() => regenerateProduct(product.id)} 
                style={{ 
                  padding: '8px 16px', 
                  background: '#3498db', 
                  color: 'white', 
                  border: 'none', 
                  borderRadius: '4px', 
                  cursor: 'pointer', 
                  fontWeight: 600,
                  fontSize: '0.9rem'
                }}
              >
                🔄 Regenerate with Category
              </button>
            </div>
            <div>
              <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Short Description:</label>
              <textarea value={product.descriptions?.shortDescription || ''} onChange={(e) => updateProductDescription(product.id, 'shortDescription', e.target.value)} rows={3} style={{ ...INPUT_BASE, resize: 'vertical' }} />
            </div>
            <div>
              <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Meta Description:</label>
              <textarea value={product.descriptions?.metaDescription || ''} onChange={(e) => updateProductDescription(product.id, 'metaDescription', e.target.value)} rows={2} style={{ ...INPUT_BASE, resize: 'vertical' }} />
              <span style={{ fontSize: '0.8rem', color: '#7f8c8d' }}>
                {(product.descriptions?.metaDescription || '').length}/160 characters
              </span>
            </div>
            <div>
              <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Long Description:</label>
              <textarea value={product.descriptions?.longDescription || ''} onChange={(e) => updateProductDescription(product.id, 'longDescription', e.target.value)} rows={6} style={{ ...INPUT_BASE, resize: 'vertical' }} />
            </div>
          </div>
        </div>
      ))}
    </>
  );

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      {/* Eva Header with Logo */}
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1rem', marginBottom: '1rem' }}>
          <img
            src="/eva.png"
            alt="Eva Robot"
            style={{
              width: '80px',
              height: '80px',
              objectFit: 'contain'
            }}
            onError={(e) => { 
              (e.currentTarget as HTMLImageElement).style.display = 'none';
            }}
          />
          <div>
            <h1 style={{ fontSize: '2.5rem', margin: 0, color: '#2c3e50' }}>Eva</h1>
            <p style={{ fontSize: '1.2rem', color: '#7f8c8d', margin: '0.5rem 0 0' }}>Enhanced Virtual Assistant</p>
          </div>
        </div>
        <p style={{ fontSize: '1.1rem', color: '#555' }}>
          Upload your product data and generate professional descriptions with brand voice
        </p>
      </div>

      {/* INPUT STEP */}
      {step === 'input' && (
        <>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => {
                  setActiveTab(tab.key);
                  setSelectedFile(null);
                  setTextInput('');
                  setImageAdditionalText('');
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
                  padding: '10px 16px',
                  border: activeTab === tab.key ? '2px solid #3498db' : BORDER_THIN,
                  background: activeTab === tab.key ? '#e3f2fd' : 'white',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: activeTab === tab.key ? 600 : 400,
                  color: activeTab === tab.key ? '#2c3e50' : '#666',
                  transition: 'all 0.2s ease',
                  fontSize: '0.95rem',
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
                  accept={activeTab === 'pdf-catalogue' ? 'application/pdf' : activeTab === 'csv' ? '.csv' : 'image/*'}
                  onChange={handleFileChange}
                  style={{ display: 'none' }}
                  id="file-upload"
                />
                <label htmlFor="file-upload" style={{ display: 'block', padding: '3rem', border: '2px dashed #bdc3c7', borderRadius: '8px', textAlign: 'center', cursor: 'pointer', background: selectedFile ? '#ecf0f1' : '#f9f9f9', transition: 'all 0.2s ease' }}>
                  <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>📤</div>
                  <p style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: '#2c3e50', fontWeight: 500 }}>
                    {selectedFile ? `Selected: ${selectedFile.name}` : 'Click to upload or drag and drop'}
                  </p>
                  <p style={{ fontSize: '0.9rem', color: '#7f8c8d' }}>
                    {activeTab === 'pdf-catalogue' && 'PDF files up to 50MB'}
                    {activeTab === 'csv' && 'CSV files'}
                    {activeTab === 'product-image' && 'JPG, PNG, or other image formats'}
                  </p>
                </label>
                
                {activeTab === 'product-image' && (
                  <div style={{ marginTop: '1rem' }}>
                    <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Additional Product Information (optional):</label>
                    <textarea value={imageAdditionalText} onChange={(e) => setImageAdditionalText(e.target.value)} placeholder="Add any extra product details, features, or specifications not visible in the image..." rows={4} style={{ ...INPUT_BASE, resize: 'vertical' }} />
                  </div>
                )}
              </>
            )}

            {!isFileTab && activeTab === 'manual-codes' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <p style={{ fontSize: '0.95rem', color: '#666', marginBottom: '0.5rem' }}>Enter at least one search criterion to find products:</p>
                <div>
                  <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>SKU:</label>
                  <input type="text" value={searchSKU} onChange={(e) => setSearchSKU(e.target.value)} placeholder="e.g., SKU123" style={{ ...INPUT_BASE }} />
                </div>
                <div>
                  <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Barcode:</label>
                  <input type="text" value={searchBarcode} onChange={(e) => setSearchBarcode(e.target.value)} placeholder="e.g., 1234567890123" style={{ ...INPUT_BASE }} />
                </div>
                <div>
                  <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>EAN:</label>
                  <input type="text" value={searchEAN} onChange={(e) => setSearchEAN(e.target.value)} placeholder="e.g., 5012345678900" style={{ ...INPUT_BASE }} />
                </div>
                <div>
                  <label style={{ fontWeight: 500, display: 'block', marginBottom: '4px' }}>Text Search:</label>
                  <input type="text" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="e.g., product name or description" style={{ ...INPUT_BASE }} />
                </div>
              </div>
            )}

            {!isFileTab && activeTab !== 'manual-codes' && (
              <>
                <textarea 
                  value={textInput} 
                  onChange={(e) => setTextInput(e.target.value)} 
                  placeholder={activeTab === 'website-url' ? 'Enter product URL\nExample: http://example.com/product/12345' : 'Enter product description or details...'} 
                  rows={8} 
                  style={{ ...INPUT_BASE, resize: 'vertical' }} 
                />
                {activeTab === 'website-url' && (
                  <p style={{ fontSize: '0.85rem', color: '#e67e22', marginTop: '0.5rem', lineHeight: '1.4' }}>
                    ⚠️ <strong>Note:</strong> Some websites block automated scraping for security. 
                    If scraping fails, please use the <strong>Free Text</strong> tab to paste product details manually.
                  </p>
                )}
              </>
            )}
          </div>

          <button onClick={handleProcess} disabled={!canProcess} style={{ marginTop: '1.5rem', padding: '12px 32px', border: 'none', borderRadius: '6px', background: canProcess ? '#27ae60' : '#bdc3c7', color: '#fff', cursor: canProcess ? 'pointer' : 'not-allowed', fontSize: '1rem', fontWeight: 600, transition: 'all 0.2s ease' }}>
            Process
          </button>
        </>
      )}

      {/* PROCESSING STEP - Show loading */}
      {step === 'processing' && (
        <div style={{ textAlign: 'center', padding: '3rem' }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>⏳</div>
          <p style={{ fontSize: '1.2rem', color: '#2c3e50', fontWeight: 500 }}>{statusMsg || 'Processing...'}</p>
          <p style={{ fontSize: '0.9rem', color: '#7f8c8d', marginTop: '0.5rem' }}>
            This may take a few minutes for large files
          </p>
        </div>
      )}

      {/* COMPLETE STEP - Show products and export options */}
      {step === 'complete' && renderProductEditor()}
    </div>
  );
};

export default UniversalUploader;
