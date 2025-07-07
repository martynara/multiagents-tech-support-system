import json
import os
import sys
import pypdfium2 as pdfium
from langchain.text_splitter import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=2000,
    chunk_overlap=200,
    length_function=len,
    separators=["\n\n", "\n", r"(?<=\. )", r"(?<=\? )", r"(?<=\! )", " ", ""],
    is_separator_regex=True,
)

def split_data_from_file(file_path):
    chunks_with_metadata = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            file_as_object = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading {file_path}: {e}")
        return chunks_with_metadata
    
    keys = list(file_as_object.keys())
    print(f"Found {len(keys)} pages in {file_path}")
    
    for item in keys:
        print(f'Processing {item} from {os.path.basename(file_path)}')
        
        item_text = file_as_object[item]
        item_text_chunks = text_splitter.split_text(item_text)
        
        form_name = os.path.splitext(os.path.basename(file_path))[0]
        
        chunk_seq_id = 0
        for chunk in item_text_chunks:
            chunks_with_metadata.append({
                'text': chunk,
                'Source': item,
                'chunkSeqId': chunk_seq_id,
                'chunkId': f'{form_name}-{item}-chunk{chunk_seq_id:04d}',
            })
            chunk_seq_id += 1
        
        print(f'\tSplit into {chunk_seq_id} chunks')
    
    return chunks_with_metadata

def extract_text_from_pdf(pdf_path):
    text_by_page = {}
    pdf = None
    
    try:
        pdf = pdfium.PdfDocument(pdf_path)
        
        for page_number in range(len(pdf)):
            try:
                page = pdf[page_number]
                textpage = page.get_textpage()
                text = textpage.get_text_bounded()
                if text.strip():
                    text_by_page[f"page_{page_number+1}"] = text
                textpage.close()
                page.close()
            except Exception as e:
                print(f"Error extracting text from page {page_number + 1}: {e}")
                continue
                
    except Exception as e:
        print(f"Error opening PDF {pdf_path}: {e}")
    finally:
        if pdf is not None:
            pdf.close()
    
    return text_by_page

def main():
    docs_dir = "data/docs"
    json_dir = "data/json"
    
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
        print(f"Created {docs_dir} directory. Please add PDF files there and run again.")
        sys.exit(0)
    
    try:
        pdf_files = [f for f in os.listdir(docs_dir) if f.lower().endswith('.pdf')]
    except OSError as e:
        print(f"Error accessing {docs_dir}: {e}")
        sys.exit(1)
    
    if not pdf_files:
        print(f"No PDF files found in {docs_dir} directory.")
        sys.exit(0)
    
    if not os.path.exists(json_dir):
        os.makedirs(json_dir)
    
    total_chunks = 0
    
    for pdf_file in pdf_files:
        pdf_path = os.path.join(docs_dir, pdf_file)
        print(f"Extracting text from {pdf_path}")
        
        text_by_page = extract_text_from_pdf(pdf_path)
        
        if not text_by_page:
            print(f"No text extracted from {pdf_file}")
            continue
        
        json_filename = os.path.join(json_dir, f"{os.path.splitext(pdf_file)[0]}.json")
        
        temp_json = os.path.join(json_dir, f"temp_{os.path.splitext(pdf_file)[0]}.json")
        try:
            with open(temp_json, "w", encoding="utf-8") as f:
                json.dump(text_by_page, f, ensure_ascii=False, indent=2)
            
            chunks = split_data_from_file(temp_json)
            
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(chunks, f, ensure_ascii=False, indent=2)
            
            os.remove(temp_json)
            
            total_chunks += len(chunks)
            print(f"Processed {pdf_file}: {len(chunks)} chunks saved to {json_filename}")
            
        except IOError as e:
            print(f"Error processing {pdf_file}: {e}")
            continue
    
    print(f"Total chunks extracted: {total_chunks}")
    print("Processing complete!")

if __name__ == "__main__":
    main()