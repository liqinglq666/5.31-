import os, time, sys

os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '600'
os.environ['HF_HUB_ETAG_TIMEOUT'] = '600'

for attempt in range(3):
    print(f'[Attempt {attempt+1}/3] Pre-downloading Docling models...')
    try:
        from docling.document_converter import DocumentConverter
        from docling.datamodel.document import ConversionStatus

        converter = DocumentConverter()

        # 创建 dummy PDF 触发所有懒加载模型（OCR、layout、table 等）
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import A4
        dummy_pdf = '/tmp/dummy_docling.pdf'
        c = canvas.Canvas(dummy_pdf, pagesize=A4)
        c.drawString(100, 700, 'Hello World')
        c.save()

        # 走一次完整转换，触发所有模型下载
        result = converter.convert(dummy_pdf)
        if result.document:
            print(f'  Dummy conversion OK (pages={len(result.document.pages)})')
        else:
            print('  Dummy conversion returned no pages')

        # 也尝试 OCR 路径（构造一张带文字的图）
        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new('RGB', (400, 100), 'white')
            draw = ImageDraw.Draw(img)
            draw.text((10, 40), 'Test', fill='black')
            img.save('/tmp/dummy_ocr.png')
            result2 = converter.convert('/tmp/dummy_ocr.png')
            print('  Image OCR conversion OK')
        except Exception as ocr_e:
            print(f'  Image OCR skipped: {ocr_e}')

        # 清理临时文件
        for f in [dummy_pdf, '/tmp/dummy_ocr.png']:
            try:
                os.remove(f)
            except:
                pass

        print('Docling models pre-downloaded successfully')
        sys.exit(0)
    except Exception as e:
        print(f'  Failed: {e}')
        if attempt < 2:
            time.sleep(10)

print('ERROR: Failed to pre-download Docling models after 3 attempts')
sys.exit(1)
