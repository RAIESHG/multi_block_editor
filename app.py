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

def get_all_files_block_attributes(files, block_name, selected_layout):
    """Get attributes for a specific block from all uploaded files."""
    all_file_attributes = {}
    
    for file in files:
        try:
            # Process the file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp_file:
                tmp_file.write(file.getvalue())
                tmp_file_path = tmp_file.name
            
            doc = ezdxf.readfile(tmp_file_path)
            attributes = get_block_attributes(doc, block_name, selected_layout)
            
            # Store attributes with filename as key
            all_file_attributes[file.name] = attributes
            
            # Clean up
            os.unlink(tmp_file_path)
            
        except Exception as e:
            st.error(f"Error processing {file.name}: {str(e)}")
    
    return all_file_attributes

def main():
    st.title("DXF Template Editor")
    st.write("Upload your DXF template file to begin editing blocks and attributes.")

    # Initialize session state for storing the DXF document and edited attributes
    if 'dxf_doc' not in st.session_state:
        st.session_state.dxf_doc = None
    if 'edited_attributes' not in st.session_state:
        st.session_state.edited_attributes = {}
    if 'selected_layout' not in st.session_state:
        st.session_state.selected_layout = 'Model Space'
    if 'attribute_values' not in st.session_state:
        st.session_state.attribute_values = {}

    # File upload section - Change to accept multiple files
    uploaded_files = st.file_uploader("Choose DXF files", type=['dxf'], accept_multiple_files=True)

    # Add a container to show uploaded files
    if uploaded_files:
        st.write(f"Uploaded {len(uploaded_files)} files:")
        for file in uploaded_files:
            st.write(f"- {file.name}")

    if uploaded_files:
        # Process the first file to get block information (we'll use this as reference)
        doc, blocks_df, layouts = process_dxf_file(uploaded_files[0])
        if doc is not None and blocks_df is not None:
            st.session_state.dxf_doc = doc  # Store first doc as reference
            
            # Store all uploaded files in session state
            if 'uploaded_files' not in st.session_state:
                st.session_state.uploaded_files = uploaded_files
            
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
                        
                        # Add radio button for editing mode
                        edit_mode = st.radio(
                            "Edit Mode",
                            ["Edit All Files Together", "Edit Each File Separately"],
                            key=f"edit_mode_{block_name}"
                        )
                        
                        if edit_mode == "Edit Each File Separately":
                            # Get attributes for each file
                            all_file_attributes = get_all_files_block_attributes(
                                uploaded_files,
                                block_name,
                                st.session_state.selected_layout
                            )
                            
                            # Create a form for editing all files
                            with st.form(key=f"form_{block_name}_all_files"):
                                st.write("Edit attribute values for all files:")
                                
                                # Initialize combined DataFrame if not exists
                                if f"{block_name}_combined" not in st.session_state.attribute_values:
                                    # Create DataFrame with combined data
                                    combined_data = []
                                    for file in uploaded_files:
                                        attributes = all_file_attributes.get(file.name, [])
                                        if attributes:
                                            # Create a row for this file
                                            row_data = {
                                                'source_file': file.name,
                                                'output_filename': f"{os.path.splitext(file.name)[0]}_{block_name}"
                                            }
                                            # Add attribute values
                                            for attr in attributes:
                                                row_data[attr['tag']] = attr['value']
                                            combined_data.append(row_data)
                                    
                                    # Create DataFrame with all columns
                                    all_columns = ['source_file', 'output_filename']
                                    for file_attrs in all_file_attributes.values():
                                        for attr in file_attrs:
                                            if attr['tag'] not in all_columns:
                                                all_columns.append(attr['tag'])
                                    
                                    # Create DataFrame with all columns
                                    df = pd.DataFrame(combined_data, columns=all_columns)
                                    st.session_state.attribute_values[f"{block_name}_combined"] = df
                                
                                # Display the combined table
                                edited_df = st.data_editor(
                                    st.session_state.attribute_values[f"{block_name}_combined"],
                                    num_rows="dynamic",
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        "source_file": st.column_config.TextColumn(
                                            "Source File",
                                            help="Original DXF file",
                                            width="medium",
                                            disabled=True
                                        ),
                                        "output_filename": st.column_config.TextColumn(
                                            "Output Filename",
                                            help="Name for the generated file",
                                            width="medium"
                                        )
                                    }
                                )
                                
                                # Add row management buttons
                                col1, col2 = st.columns(2)
                                with col1:
                                    # Add a number input for specifying how many copies
                                    num_copies = st.number_input(
                                        "Number of copies per file:", 
                                        min_value=1, 
                                        max_value=100, 
                                        value=1, 
                                        step=1, 
                                        key=f"num_copies_{block_name}"
                                    )
                                    
                                    if st.form_submit_button("Add Copies"):
                                        current_df = st.session_state.attribute_values[f"{block_name}_combined"]
                                        new_rows = []
                                        
                                        # For each existing row, create copies
                                        for _, row in current_df.iterrows():
                                            for i in range(num_copies):
                                                new_row = row.copy()
                                                base_name = os.path.splitext(row['output_filename'])[0]
                                                new_row['output_filename'] = f"{base_name}_{i+1}"
                                                new_rows.append(new_row)
                                        
                                        # Add new rows to DataFrame
                                        new_df = pd.DataFrame(new_rows)
                                        st.session_state.attribute_values[f"{block_name}_combined"] = pd.concat(
                                            [current_df, new_df], 
                                            ignore_index=True
                                        )
                                        st.rerun()
                                
                                with col2:
                                    if st.form_submit_button("Remove Selected Rows"):
                                        # Remove rows (will be implemented when selection is added)
                                        pass
                                
                                # Save changes button
                                if st.form_submit_button("Save Changes"):
                                    st.session_state.attribute_values[f"{block_name}_combined"] = edited_df
                                    st.success("Changes saved!")
                            
                            # Generate files button
                            if st.button(f"Generate All DXF Files"):
                                # Process each file
                                all_generated_files = []
                                all_original_filenames = []
                                
                                # Group the DataFrame by source file
                                grouped_df = edited_df.groupby('source_file')
                                
                                for file in uploaded_files:
                                    if file.name in grouped_df.groups:
                                        file_rows = grouped_df.get_group(file.name)
                                        
                                        # Create attribute values for this file
                                        attribute_values = []
                                        for _, row in file_rows.iterrows():
                                            filename = row['output_filename']
                                            # Get all attribute values (excluding source_file and output_filename)
                                            attrs = {k: v for k, v in row.items() 
                                                   if k not in ['source_file', 'output_filename']}
                                            attribute_values.append((filename, attrs))
                                        
                                        # Process this file
                                        doc, _, _ = process_dxf_file(file)
                                        generated_files, original_filenames = generate_dxf_files(
                                            doc,
                                            block_name,
                                            attribute_values
                                        )
                                        
                                        all_generated_files.extend(generated_files)
                                        all_original_filenames.extend(original_filenames)
                                
                                # Handle downloads
                                if all_generated_files:
                                    st.success(f"Generated {len(all_generated_files)} DXF files:")
                                    
                                    # Create a mapping of file paths to original filenames
                                    filename_map = {path: name for path, name in all_original_filenames}
                                    
                                    # Create ZIP file with all generated files
                                    zip_buffer = BytesIO()
                                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                        for file_path in all_generated_files:
                                            original_name = filename_map[file_path]
                                            with open(file_path, 'rb') as f:
                                                zip_file.writestr(f"{original_name}.dxf", f.read())
                                    
                                    zip_buffer.seek(0)
                                    
                                    # Download button for all files
                                    st.download_button(
                                        label=f"Download All Generated Files ({len(all_generated_files)} files)",
                                        data=zip_buffer,
                                        file_name=f"{block_name}_all_files.zip",
                                        mime="application/zip",
                                        key="download_all_combined"
                                    )
                        else:  # Edit All Files Together
                            # Get attributes from the first file (reference)
                            attributes = get_block_attributes(
                                st.session_state.dxf_doc, 
                                block_name,
                                st.session_state.selected_layout
                            )
                            
                            if not attributes:
                                st.info("No attributes found in this block.")
                                continue
                            
                            # Create a form for editing all files together
                            with st.form(key=f"form_{block_name}_all_together"):
                                st.write("Edit attribute values for all files:")
                                
                                # Initialize DataFrame if not exists
                                if f"{block_name}_all_together" not in st.session_state.attribute_values:
                                    # Create DataFrame with just the attributes and their current values
                                    df = pd.DataFrame(columns=['attribute', 'new_value'])
                                    for attr in attributes:
                                        df.loc[len(df)] = {
                                            'attribute': attr['tag'],
                                            'new_value': ''  # Start with empty values
                                        }
                                    st.session_state.attribute_values[f"{block_name}_all_together"] = df
                                
                                # Display the table
                                edited_df = st.data_editor(
                                    st.session_state.attribute_values[f"{block_name}_all_together"],
                                    num_rows="fixed",
                                    use_container_width=True,
                                    hide_index=True,
                                    column_config={
                                        "attribute": st.column_config.TextColumn(
                                            "Attribute",
                                            help="Attribute name",
                                            width="medium",
                                            disabled=True
                                        ),
                                        "new_value": st.column_config.TextColumn(
                                            "New Value",
                                            help="New value to set for all files (leave empty to keep current value)",
                                            width="medium"
                                        )
                                    }
                                )
                                
                                # Save changes button
                                if st.form_submit_button("Save Changes"):
                                    st.session_state.attribute_values[f"{block_name}_all_together"] = edited_df
                                    st.success("Changes saved!")
                            
                            # Generate files button
                            if st.button(f"Generate All DXF Files"):
                                # Get the edited values
                                edited_values = {}
                                current_df = st.session_state.attribute_values[f"{block_name}_all_together"]
                                
                                # Debug: Show the current DataFrame
                                st.write("Current values in DataFrame:")
                                st.dataframe(current_df)
                                
                                for _, row in current_df.iterrows():
                                    if row['new_value'] and row['new_value'].strip():  # Check if value exists and is not just whitespace
                                        edited_values[row['attribute']] = str(row['new_value'])
                                
                                # Debug: Show the edited values
                                st.write("Values to be updated:")
                                st.write(edited_values)
                                
                                if not edited_values:
                                    st.warning("No values have been changed. Please enter at least one value to update.")
                                    return
                                
                                # Process each file
                                all_generated_files = []
                                all_original_filenames = []
                                
                                for file in st.session_state.uploaded_files:
                                    try:
                                        # Save the uploaded file to a temporary file
                                        with tempfile.NamedTemporaryFile(delete=False, suffix='.dxf') as tmp_file:
                                            tmp_file.write(file.getvalue())
                                            tmp_file_path = tmp_file.name
                                        
                                        # Read the DXF file
                                        doc = ezdxf.readfile(tmp_file_path)
                                        
                                        # Generate new DXF file with updated attributes
                                        generated_files, original_filenames = generate_dxf_files(
                                            doc,
                                            block_name,
                                            [(file.name, edited_values)]  # Pass as list of tuples with filename and values
                                        )
                                        all_generated_files.extend(generated_files)
                                        all_original_filenames.extend(original_filenames)
                                        
                                        # Clean up the temporary input file
                                        os.unlink(tmp_file_path)
                                    except Exception as e:
                                        st.error(f"Error processing file {file.name}: {str(e)}")
                                        continue
                                
                                if not all_generated_files:
                                    st.error("Failed to generate any DXF files.")
                                    return
                                
                                # Create a mapping of file paths to original filenames
                                filename_map = {path: name for path, name in all_original_filenames}
                                
                                # Create ZIP file with all generated files
                                zip_buffer = BytesIO()
                                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                    for file_path in all_generated_files:
                                        original_name = filename_map[file_path]
                                        with open(file_path, 'rb') as f:
                                            zip_file.writestr(original_name, f.read())  # Use original filename
                                
                                zip_buffer.seek(0)
                                
                                # Download button for all files
                                st.download_button(
                                    label=f"Download All Generated Files ({len(all_generated_files)} files)",
                                    data=zip_buffer,
                                    file_name=f"{block_name}_all_files.zip",
                                    mime="application/zip",
                                    key="download_all_combined"
                                )

if __name__ == "__main__":
    main() 