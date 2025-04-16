import streamlit as st
import ezdxf
import pandas as pd
from io import BytesIO
import tempfile
import os
import zipfile

st.set_page_config(page_title="DXF Template Editor", layout="wide")

def process_dxf_file(uploaded_file):
    """Process the uploaded DXF file and extract block information."""
    try:
        # Save the uploaded file to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name

        # Read the DXF file
        doc = ezdxf.readfile(tmp_file_path)

        # Get all available layouts
        layouts = ['Model Space']  # Always include Model Space
        for layout in doc.layouts:
            if layout.name != 'Model':  # Skip Model as we already have Model Space
                layouts.append(layout.name)

        # Extract block information
        blocks = []
        for block in doc.blocks:
            has_attributes = False
            # Check block definition
            for entity in block:
                if entity.dxftype() == 'ATTRIB':
                    has_attributes = True
                    break
            
            blocks.append({
                'name': block.name,
                'entities': len(block),
                'has_attributes': has_attributes
            })

        # Clean up the temporary file
        os.unlink(tmp_file_path)

        return doc, pd.DataFrame(blocks), layouts
    except Exception as e:
        st.error(f"Error processing DXF file: {str(e)}")
        return None, None, []

def get_block_attributes(doc, block_name, selected_layout):
    """Get attributes for a specific block in the selected layout."""
    try:
        attributes = []
        block = doc.blocks.get(block_name)
        
        if block is None:
            return []
        
        # First check block definition
        for entity in block:
            if entity.dxftype() == 'ATTRIB':
                attributes.append({
                    'tag': entity.dxf.tag,
                    'value': entity.dxf.text,
                    'prompt': entity.dxf.prompt if hasattr(entity.dxf, 'prompt') else ''
                })
        
        # Then check block references in the selected layout
        if selected_layout == 'Model Space':
            space = doc.modelspace()
        else:
            try:
                space = doc.layouts.get(selected_layout)
                if space is None:
                    st.error(f"Layout '{selected_layout}' not found in the document")
                    return attributes
            except Exception as e:
                st.error(f"Error accessing layout '{selected_layout}': {str(e)}")
                return attributes
        
        # Query for INSERT entities in the selected space
        for insert in space.query('INSERT'):
            if insert.dxf.name == block_name:
                for attrib in insert.attribs:
                    attributes.append({
                        'tag': attrib.dxf.tag,
                        'value': attrib.dxf.text,
                        'prompt': attrib.dxf.prompt if hasattr(attrib.dxf, 'prompt') else ''
                    })
        
        # Remove duplicates based on tag
        seen_tags = set()
        unique_attributes = []
        for attr in attributes:
            if attr['tag'] not in seen_tags:
                seen_tags.add(attr['tag'])
                unique_attributes.append(attr)
        
        return unique_attributes
    except Exception as e:
        st.error(f"Error getting attributes for block {block_name}: {str(e)}")
        return []

def generate_dxf_files(doc, block_name, attribute_values):
    """Generate multiple DXF files based on attribute values."""
    try:
        # Create a temporary directory for the generated files
        temp_dir = tempfile.mkdtemp()
        generated_files = []
        original_filenames = []  # Add this line to track original filenames

        # For each set of attribute values (filename and attrs)
        for filename, values in attribute_values:
            print(f"Processing file: {filename}")
            print(f"Values to update: {values}")
            
            # Sanitize filename for filesystem
            safe_filename = "".join([c for c in filename if c.isalnum() or c in "._- "])
            
            # Create a deep copy of the original document
            temp_file = os.path.join(temp_dir, f"{safe_filename}.dxf")
            doc.saveas(temp_file)
            
            # Store the original filename with the path
            original_filenames.append((temp_file, filename))  # Keep track of original filename
            
            # Open the new file for editing
            new_doc = ezdxf.readfile(temp_file)
            
            # Update block definition first
            block = new_doc.blocks.get(block_name)
            if block:
                for entity in block:
                    if entity.dxftype() == 'ATTRIB':
                        if entity.dxf.tag in values:
                            print(f"Updating block definition - Tag: {entity.dxf.tag}, Old value: {entity.dxf.text}, New value: {values[entity.dxf.tag]}")
                            entity.dxf.text = str(values[entity.dxf.tag])
                            entity.dxf.invisible = 0  # Make attribute visible
            
            # Track if we found and updated any attributes
            updates_made = False
            
            # Update attributes in all layouts - corrected iteration method
            for layout in new_doc.layouts:
                layout_name = layout.name
                print(f"Checking layout: {layout_name}")
                for insert in layout.query('INSERT'):
                    if insert.dxf.name == block_name:
                        print(f"Found block {block_name} in layout {layout_name}")
                        for attrib in insert.attribs:
                            if attrib.dxf.tag in values:
                                print(f"Updating layout attribute - Tag: {attrib.dxf.tag}, Old value: {attrib.dxf.text}, New value: {values[attrib.dxf.tag]}")
                                attrib.dxf.text = str(values[attrib.dxf.tag])
                                attrib.dxf.invisible = 0
                                updates_made = True
            
            # Update attributes in modelspace
            print("Checking modelspace")
            for insert in new_doc.modelspace().query('INSERT'):
                if insert.dxf.name == block_name:
                    print(f"Found block {block_name} in modelspace")
                    for attrib in insert.attribs:
                        if attrib.dxf.tag in values:
                            print(f"Updating modelspace attribute - Tag: {attrib.dxf.tag}, Old value: {attrib.dxf.text}, New value: {values[attrib.dxf.tag]}")
                            attrib.dxf.text = str(values[attrib.dxf.tag])
                            attrib.dxf.invisible = 0
                            updates_made = True
            
            if not updates_made:
                print("WARNING: No attributes were updated in this file!")
            
            # Make sure to save and audit the document - removed compress parameter
            print(f"Saving file: {temp_file}")
            new_doc.save()
            
            # Verify the file was saved correctly
            file_size = os.path.getsize(temp_file)
            print(f"File saved with size: {file_size} bytes")
            
            generated_files.append(temp_file)

        return generated_files, original_filenames  # Return both lists
    except Exception as e:
        print(f"Error in generate_dxf_files: {str(e)}")
        st.error(f"Error generating DXF files: {str(e)}")
        return [], []

def process_multiple_dxf_files(files, block_name, attribute_values):
    """Process multiple DXF files and update the specified block attributes in all of them."""
    try:
        # Create a temporary directory for the generated files
        temp_dir = tempfile.mkdtemp()
        generated_files = []
        original_filenames = []

        # Process each uploaded file
        for uploaded_file in files:
            # Save the uploaded file to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name

            # Read the DXF file
            doc = ezdxf.readfile(tmp_file_path)

            # For each set of attribute values (filename and attrs)
            for filename, values in attribute_values:
                print(f"Processing file: {uploaded_file.name} with values for {filename}")
                
                # Create output filename by combining original filename and attribute filename
                base_name = os.path.splitext(uploaded_file.name)[0]
                output_filename = f"{base_name}_{filename}"
                safe_filename = "".join([c for c in output_filename if c.isalnum() or c in "._- "])
                
                # Create a copy of the document
                temp_file = os.path.join(temp_dir, f"{safe_filename}.dxf")
                doc.saveas(temp_file)
                
                # Store the original filename with the path
                original_filenames.append((temp_file, output_filename))
                
                # Open the new file for editing
                new_doc = ezdxf.readfile(temp_file)
                
                # Update block definition first
                block = new_doc.blocks.get(block_name)
                if block:
                    for entity in block:
                        if entity.dxftype() == 'ATTRIB':
                            if entity.dxf.tag in values:
                                entity.dxf.text = str(values[entity.dxf.tag])
                                entity.dxf.invisible = 0
                
                # Update attributes in all layouts
                for layout in new_doc.layouts:
                    for insert in layout.query('INSERT'):
                        if insert.dxf.name == block_name:
                            for attrib in insert.attribs:
                                if attrib.dxf.tag in values:
                                    attrib.dxf.text = str(values[attrib.dxf.tag])
                                    attrib.dxf.invisible = 0
                
                # Update attributes in modelspace
                for insert in new_doc.modelspace().query('INSERT'):
                    if insert.dxf.name == block_name:
                        for attrib in insert.attribs:
                            if attrib.dxf.tag in values:
                                attrib.dxf.text = str(values[attrib.dxf.tag])
                                attrib.dxf.invisible = 0
                
                # Save the modified document
                new_doc.save()
                generated_files.append(temp_file)

            # Clean up the temporary input file
            os.unlink(tmp_file_path)

        return generated_files, original_filenames
    except Exception as e:
        print(f"Error in process_multiple_dxf_files: {str(e)}")
        st.error(f"Error processing multiple DXF files: {str(e)}")
        return [], []

def main():
    st.title("DXF Template Editor")
    st.write("Upload your DXF template file to begin editing blocks and attributes.")

    # Initialize session state
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = None
    if 'dxf_doc' not in st.session_state:
        st.session_state.dxf_doc = None
    if 'edited_attributes' not in st.session_state:
        st.session_state.edited_attributes = {}
    if 'selected_layout' not in st.session_state:
        st.session_state.selected_layout = 'Model Space'
    if 'attribute_values' not in st.session_state:
        st.session_state.attribute_values = {}

    # File upload section with clear instructions
    st.write("### Upload DXF Files")
    st.write("You can select multiple files by holding Ctrl (Windows) or Command (Mac) while selecting files.")
    uploaded_files = st.file_uploader(
        "Choose one or more DXF files",
        type=['dxf'],
        accept_multiple_files=True,
        key='file_uploader'
    )

    # Store uploaded files in session state
    if uploaded_files:
        st.session_state.uploaded_files = uploaded_files
        
        # Display uploaded files information
        st.write("### Uploaded Files:")
        for idx, file in enumerate(uploaded_files, 1):
            st.write(f"{idx}. {file.name}")
        
        # Process the first file as template
        doc, blocks_df, layouts = process_dxf_file(uploaded_files[0])
        
        if doc is not None and blocks_df is not None:
            st.session_state.dxf_doc = doc
            
            # Layout selection
            st.session_state.selected_layout = st.selectbox(
                "Select Layout/Space to check for attributes",
                options=layouts,
                index=0
            )
            
            st.subheader("Available Blocks")
            st.dataframe(blocks_df)
            
            # Block selection
            selected_blocks = st.multiselect(
                "Select blocks to edit",
                options=blocks_df['name'].tolist()
            )
            
            if selected_blocks:
                st.subheader("Edit Block Attributes")
                st.write(f"Checking attributes in: {st.session_state.selected_layout}")
                
                # Create tabs for each selected block
                tabs = st.tabs(selected_blocks)
                
                for i, block_name in enumerate(selected_blocks):
                    with tabs[i]:
                        st.write(f"Editing block: {block_name}")
                        
                        # Get attributes for the block
                        attributes = get_block_attributes(
                            st.session_state.dxf_doc, 
                            block_name,
                            st.session_state.selected_layout
                        )
                        
                        if not attributes:
                            st.info("No attributes found in this block.")
                            continue
                        
                        # Initialize attribute values for this block if not exists
                        if block_name not in st.session_state.attribute_values:
                            # Create DataFrame with attributes and filename column
                            columns = ['filename'] + [attr['tag'] for attr in attributes]
                            st.session_state.attribute_values[block_name] = pd.DataFrame(
                                columns=columns
                            )
                            # Add one empty row with default filename
                            default_filename = f"{block_name}_1"
                            st.session_state.attribute_values[block_name].loc[0] = {
                                'filename': default_filename,
                                **{attr['tag']: attr['value'] for attr in attributes}
                            }
                        
                        # Create a form for editing attribute values
                        with st.form(key=f"form_{block_name}"):
                            st.write("Edit attribute values:")
                            
                            # Display the current values in a table
                            edited_df = st.data_editor(
                                st.session_state.attribute_values[block_name],
                                num_rows="dynamic",
                                use_container_width=True,
                                hide_index=False,
                                key=f"editor_{block_name}"  # Add a unique key for the editor
                            )
                            
                            # Add/remove rows buttons
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                # Add a number input for specifying how many rows to add
                                num_rows_to_add = st.number_input("Rows to add:", min_value=1, max_value=100, value=1, step=1, key=f"num_rows_{block_name}")
                                
                                if st.form_submit_button("Add Rows"):
                                    # Get the current state of the DataFrame
                                    current_df = st.session_state.attribute_values[block_name]
                                    
                                    # Get the starting index for new rows
                                    start_idx = len(current_df)
                                    
                                    # Add the specified number of rows
                                    for i in range(num_rows_to_add):
                                        # Create a new row with values from the first row
                                        new_row = current_df.iloc[0].copy()
                                        
                                        # Set a default filename for the new row with incrementing number
                                        new_row['filename'] = f"{block_name}_{start_idx + i + 1}"
                                        
                                        # Add the new row to the DataFrame
                                        current_df.loc[len(current_df)] = new_row
                                    
                                    # Update the session state
                                    st.session_state.attribute_values[block_name] = current_df
                                    
                                    # Rerun to update the display
                                    st.rerun()

                            with col2:
                                if st.form_submit_button("Remove Last Row"):
                                    if len(st.session_state.attribute_values[block_name]) > 1:
                                        st.session_state.attribute_values[block_name] = st.session_state.attribute_values[block_name].iloc[:-1]
                                        st.rerun()
                            
                            with col3:
                                # Add option to remove multiple rows
                                num_rows_to_remove = st.number_input("Rows to remove:", min_value=1, max_value=100, value=1, step=1, key=f"num_remove_{block_name}")
                                
                                if st.form_submit_button("Remove Multiple Rows"):
                                    current_df = st.session_state.attribute_values[block_name]
                                    # Make sure we don't remove all rows
                                    rows_to_keep = max(1, len(current_df) - num_rows_to_remove)
                                    if len(current_df) > 1:
                                        st.session_state.attribute_values[block_name] = current_df.iloc[:rows_to_keep]
                                        st.rerun()
                            
                            # Update the values in session state when form is submitted
                            if st.form_submit_button("Save Changes"):
                                st.session_state.attribute_values[block_name] = edited_df
                                st.success("Changes saved!")
                        
                        # Add a checkbox to enable multi-file processing
                        process_all_files = st.checkbox("Process all uploaded files", key=f"process_all_{block_name}")

                        if st.button(f"Generate DXF Files for {block_name}"):
                            # Use the latest saved values from session state
                            print(f"DataFrame contents for {block_name}:")
                            print(st.session_state.attribute_values[block_name])
                            
                            # Convert DataFrame to list of tuples (filename, attributes)
                            attribute_values = []
                            for _, row in st.session_state.attribute_values[block_name].iterrows():
                                filename = row['filename']
                                attrs = {k: v for k, v in row.items() if k != 'filename'}
                                attribute_values.append((filename, attrs))
                            
                            # Force a conversion to strings for all values
                            attribute_values = [(name, {k: str(v) for k, v in attrs.items()}) 
                                                for name, attrs in attribute_values]
                            
                            if process_all_files and len(uploaded_files) > 1:
                                # Process all uploaded files
                                generated_files, original_filenames = process_multiple_dxf_files(
                                    uploaded_files, 
                                    block_name, 
                                    attribute_values
                                )
                            else:
                                # Process just the first file (original behavior)
                                doc, _, _ = process_dxf_file(uploaded_files[0])
                                generated_files, original_filenames = generate_dxf_files(
                                    doc, 
                                    block_name, 
                                    attribute_values
                                )

                            if generated_files:
                                st.success(f"Generated {len(generated_files)} DXF files:")
                                
                                # Create a mapping of file paths to original filenames
                                filename_map = {path: name for path, name in original_filenames}
                                
                                # Individual file download buttons
                                for file_path in generated_files:
                                    original_name = filename_map[file_path]  # Get the original filename
                                    
                                    # Force file system sync before reading
                                    with open(file_path, "rb") as f:
                                        file_data = f.read()  # Read file content into memory
                                        
                                        st.download_button(
                                            label=f"Download {original_name}.dxf",
                                            data=file_data,  # Use the in-memory data
                                            file_name=f"{original_name}.dxf",  # Use original name for download
                                            mime="application/dxf"
                                        )
                                
                                # Add Download All button if multiple files
                                if len(generated_files) > 1:
                                    # Create a ZIP file in memory
                                    zip_buffer = BytesIO()
                                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                        for file_path in generated_files:
                                            original_name = filename_map[file_path]  # Get the original filename
                                            
                                            # Add each file to the ZIP archive with the original name
                                            with open(file_path, 'rb') as f:
                                                zip_file.writestr(f"{original_name}.dxf", f.read())
                                    
                                    # Reset buffer position
                                    zip_buffer.seek(0)
                                    
                                    # Create download button for the ZIP file
                                    st.download_button(
                                        label=f"Download All Files ({len(generated_files)} DXF files)",
                                        data=zip_buffer,
                                        file_name=f"{block_name}_files.zip",
                                        mime="application/zip",
                                        key="download_all"
                                    )
                            else:
                                st.error("Failed to generate DXF files")

if __name__ == "__main__":
    main() 