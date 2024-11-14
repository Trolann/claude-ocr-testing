import pdfrw
import pdf2image
import pytesseract
from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject, TextStringObject, IndirectObject
import os
from collections import OrderedDict


def set_need_appearances_writer(writer):
    """Set up the writer to handle form field appearances."""
    try:
        catalog = writer._root_object
        if "/AcroForm" not in catalog:
            writer._root_object.update({
                NameObject("/AcroForm"): IndirectObject(len(writer._objects), 0, writer)
            })

        need_appearances = NameObject("/NeedAppearances")
        writer._root_object["/AcroForm"][need_appearances] = BooleanObject(True)
    except Exception as e:
        print(f"Error setting up appearances: {str(e)}")


def get_checkbox_states(field_obj):
    """Extract available states for a checkbox field."""
    states = []

    # Check for appearance states in the field
    if "/AP" in field_obj:
        ap_dict = field_obj["/AP"].get_object()
        if "/N" in ap_dict:
            n_dict = ap_dict["/N"].get_object()
            states.extend(k for k in n_dict.keys() if k != "/Off")

    # Check for states in field's kids
    if "/Kids" in field_obj:
        for kid in field_obj["/Kids"]:
            kid_obj = kid.get_object()
            if "/AP" in kid_obj:
                ap_dict = kid_obj["/AP"].get_object()
                if "/N" in ap_dict:
                    n_dict = ap_dict["/N"].get_object()
                    states.extend(k for k in n_dict.keys() if k != "/Off")

    # Remove duplicates while preserving order
    return list(OrderedDict.fromkeys(states))


def find_and_update_checkbox(fields, target_name, value):
    """Recursively find and update checkbox fields."""
    for field in fields:
        field_obj = field.get_object()

        # Function to update field value
        def update_field(obj):
            # Get available checked states for this checkbox
            checked_states = get_checkbox_states(obj)
            if not checked_states:
                checked_states = ['/1']  # Default if no states found

            # Choose appropriate state based on value
            checkbox_value = checked_states[0] if value else "/Off"

            print(f"Initial field state:")
            print(f"Value: {obj.get('/V', 'None')}")
            print(f"States: {checked_states + ['/Off']}")
            print(f"Found target field: {target_name}")

            obj[NameObject("/V")] = NameObject(checkbox_value)
            if "/AS" in obj:
                obj[NameObject("/AS")] = NameObject(checkbox_value)
            return True

        # Check if this is a parent field with kids
        if "/Kids" in field_obj:
            for kid in field_obj["/Kids"]:
                kid_obj = kid.get_object()
                if "/T" in kid_obj and target_name in kid_obj["/T"]:
                    return update_field(kid_obj)
            if find_and_update_checkbox(field_obj["/Kids"], target_name, value):
                return True

        # Check if this is the target field
        if "/T" in field_obj and target_name in field_obj["/T"]:
            return update_field(field_obj)

    return False


class PDFProcessor:
    def __init__(self, input_pdf_path):
        """Initialize with path to fillable PDF form."""
        self.input_pdf_path = input_pdf_path
        self.template_pdf = pdfrw.PdfReader(input_pdf_path)

    def decode_pdf_field_name(self, field_name):
        """
        Decode PDF form field names from UTF-16 encoding.
        Handles the '<FEFF...>' format commonly found in PDF forms.
        """
        if not field_name:
            return ""

        # Remove the '<FEFF' prefix and '>' suffix if present
        if field_name.startswith("<FEFF") and field_name.endswith(">"):
            field_name = field_name[5:-1]

        try:
            # Convert hex string to bytes and decode as UTF-16
            bytes_data = bytes.fromhex(field_name)
            decoded = bytes_data.decode("utf-16-be")

            # Remove common suffixes like '[0]' that appear in form fields
            if decoded.endswith("[0]"):
                decoded = decoded[:-3]

            return decoded
        except Exception as e:
            print(f"Warning: Could not decode field name {field_name}: {e}")
            return field_name

    def encode_pdf_field_name(self, field_name):
        """
        Encode a human-readable field name back to PDF format.
        """
        # Convert to UTF-16-BE bytes and then to hex
        hex_data = field_name.encode("utf-16-be").hex().upper()
        return f"<FEFF{hex_data}>"

    def is_checkbox(self, annotation):
        """
        Determine if a form field is a checkbox based on its properties.
        """
        if hasattr(annotation, 'FT'):
            return str(annotation.FT) == '/Btn'
        return False

    def fill_form(self, data_dict, output_path):
        """
        Fill PDF form with given data and save to output_path.

        Args:
            data_dict (dict): Dictionary with field names as keys and values:
                             - For text fields: string values
                             - For checkboxes: boolean values (True/False)
            output_path (str): Path where to save the filled PDF
        """
        # Create PDF reader and writer
        reader = PdfReader(self.input_pdf_path)
        writer = PdfWriter()
        writer.clone_reader_document_root(reader)

        # Get AcroForm and fields
        if "/AcroForm" in writer._root_object:
            fields = writer._root_object["/AcroForm"]["/Fields"]

            # Process each field in the data dictionary
            for field_name, value in data_dict.items():
                if isinstance(value, bool):
                    # Handle checkbox using boolean value
                    find_and_update_checkbox(fields, field_name, value)
                else:
                    # Handle text field
                    for field in fields:
                        field_obj = field.get_object()
                        if "/T" in field_obj and field_name == str(field_obj["/T"]):
                            field_obj[NameObject("/V")] = TextStringObject(str(value))
                            break

            # Ensure proper appearance of form fields
            set_need_appearances_writer(writer)

        # Save the filled PDF
        with open(output_path, 'wb') as output_file:
            writer.write(output_file)

    def get_form_fields(self):
        """Return an ordered dictionary of all fillable form fields with their current values."""
        fields = OrderedDict()

        for page_num, page in enumerate(self.template_pdf.pages):
            if page.Annots:
                # Sort annotations by their vertical position (top to bottom)
                annotations = []
                for annot in page.Annots:
                    if annot.T and hasattr(annot, 'Rect'):
                        # Get the y-coordinate (vertical position) from the annotation rectangle
                        y_pos = float(annot.Rect[1])
                        annotations.append((y_pos, annot))

                # Sort by y-position in descending order (top to bottom)
                annotations.sort(key=lambda x: x[0], reverse=True)

                # Process sorted annotations
                for _, annotation in annotations:
                    raw_key = str(annotation.T)
                    decoded_key = self.decode_pdf_field_name(raw_key)

                    # Determine if field is a checkbox
                    is_checkbox = self.is_checkbox(annotation)

                    if annotation.V:
                        value = str(annotation.V)
                        if is_checkbox:
                            # Convert checkbox values to boolean
                            value = value != "/Off"
                        fields[decoded_key] = value
                    else:
                        fields[decoded_key] = False if is_checkbox else ""

        return fields

    def convert_to_images(self, output_dir="images/"):
        """
        Convert PDF to images (one per page).

        Args:
            output_dir (str): Directory to save images

        Returns:
            list: Paths to generated images
        """
        os.makedirs(output_dir, exist_ok=True)
        images = convert_from_path(self.input_pdf_path)

        image_paths = []
        for i, image in enumerate(images):
            image_path = os.path.join(output_dir, f"page_{i + 1}.png")
            image.save(image_path, "PNG")
            image_paths.append(image_path)

        return image_paths

    def extract_text_from_pdf(self):
        """
        Extract text content from PDF.
        """
        reader = PdfReader(self.input_pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

    def extract_text_from_image(self, image_path):
        """
        Extract text from image using OCR.
        """
        return pytesseract.image_to_string(image_path)


# Example usage:
if __name__ == "__main__":
    # Sample data using boolean values for checkboxes
    data = OrderedDict([
        ('TypeOfBenefitsApplyingFor[0]', False),  # Will check the box
        ('TypeOfBenefitsApplyingFor[1]', True)  # Will uncheck the box
    ])

    try:
        # Initialize processor with your fillable PDF
        processor = PDFProcessor("Form-10-10EZ.pdf")

        # Get and print all available fields
        print("Available form fields:")
        fields = processor.get_form_fields()
        from pprint import pprint

        pprint(fields)

        # Fill the form and save
        if os.path.exists("filled_form.pdf"):
            os.remove("filled_form.pdf")
        processor.fill_form(data, "filled_form.pdf")
        print("\nForm has been filled and saved as 'filled_form.pdf'")

    except Exception as e:
        print(f"An error occurred: {str(e)}")