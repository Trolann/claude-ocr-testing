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

def find_and_update_checkbox(fields, target_name, value):
    """Recursively find and update checkbox fields."""
    for field in fields:
        field_obj = field.get_object()
        
        # Check if this is a parent field with kids
        if "/Kids" in field_obj:
            for kid in field_obj["/Kids"]:
                kid_obj = kid.get_object()
                if "/T" in kid_obj and target_name in kid_obj["/T"]:
                    checkbox_value = "/Yes" if value else "/Off"
                    kid_obj[NameObject("/V")] = NameObject(checkbox_value)
                    if "/AS" in kid_obj:
                        kid_obj[NameObject("/AS")] = NameObject(checkbox_value)
                    return True
            if find_and_update_checkbox(field_obj["/Kids"], target_name, value):
                return True

        # Check if this is the target field
        if "/T" in field_obj and target_name in field_obj["/T"]:
            checkbox_value = "/Yes" if value else "/Off"
            field_obj[NameObject("/V")] = NameObject(checkbox_value)
            if "/AS" in field_obj:
                field_obj[NameObject("/AS")] = NameObject(checkbox_value)
            return True

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
            data_dict (dict): Dictionary with human-readable field names as keys
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
                if isinstance(value, bool) or value in ['Yes', 'On', True, '/1', '/Yes', 1, 'Off', False, '/Off', 0]:
                    # Handle checkbox
                    checkbox_value = value if isinstance(value, bool) else value in ['Yes', 'On', True, '/1', '/Yes', 1]
                    find_and_update_checkbox(fields, field_name, checkbox_value)
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
        """Return an ordered dictionary of all fillable form fields with human-readable names."""
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
                            # Convert checkbox values to consistent format
                            value = 'Yes' if value in ['/Yes', '/1'] else 'Off'
                        fields[decoded_key] = value
                    else:
                        fields[decoded_key] = "Off" if is_checkbox else ""

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
    # Initialize processor with your fillable PDF
    data = OrderedDict([
        ('TypeOfBenefitsApplyingFor', '1'),
        ('TypeOfBenefitsApplyingFor[1]', 'Off'),
        ('MothersMaidenName', ''),
        ('LastFirstMiddle', ''),
        ('PreferredNameForVeteran', ''),
        ('Race', '/Off'),
        ('Race[2]', '/Off'),
        ('Race[3]', '/Off'),
        ('Race[1]', '/Off'),
        ('Race[4]', '/Off'),
        ('Race[5]', '/Off'),
        ('SSN', ''),
        ('DOB', ''),
        ('PlaceOfBirth', ''),
        ('Religion', ''),
        ('PreferredLanguage', ''),
        ('MailingAddress_Street', ''),
        ('MailingAddress_City', ''),
        ('MailingAddress_State', ''),
        ('MailingAddress_ZipCode', ''),
        ('MailingAddress_County', ''),
        ('HomeTelephoneNumber', ''),
        ('MbileTelephoneNumber', ''),
        ('EmailAddress', ''),
        ('HomeAddress_State', ''),
        ('HomeAddress_Street', ''),
        ('HomeAddress_City', ''),
        ('HomeAddress_ZipCode', ''),
        ('HomeAddress_County', ''),
        ('NextOfKinAddress', ''),
        ('NextOfKinName', ''),
        ('NextOfKinRelationship', ''),
        ('NextOfKinTelephoneNumber', ''),
        ('EmergencyContactTelephoneNumber', ''),
        ('EmergencyContactName', ''),
        ('Designee', ''),
        ('PreferredVACenter', ''),
        ('LastBranchOfService', ''),
        ('LastEntryDate', ''),
        ('LastDischargeDate', ''),
        ('FutureDischargeDate', ''),
        ('DischargeType', ''),
        ('MilitaryServiceNumber', ''),
        ('FromDate_3C', ''),
        ('ToDate_3C', ''),
        ('ExposedToTheFollowing', '/Off'),
        ('ExposedToTheFollowing[1]', '/Off'),
        ('ExposedToTheFollowing[7]', '/Off'),
        ('FromDate_3B', ''),
        ('ToDate_3B', ''),
        ('ExposedToTheFollowing[2]', '/Off'),
        ('ExposedToTheFollowing[3]', '/Off'),
        ('ExposedToTheFollowing[4]', '/Off'),
        ('ExposedToTheFollowing[5]', '/Off'),
        ('ExposedToTheFollowing[6]', '/Off'),
        ('ExposedToTheFollowing[8]', '/Off'),
        ('ExposedToTheFollowing[9]', '/Off'),
        ('SpecifyOther', ''),
        ('ToDate_3D', ''),
        ('FromDate_3D', ''),
        ('HealthInsuranceInformation', ''),
        ('NameOfPolicyHodler', ''),
        ('PolicyNumber', ''),
        ('GroupCode', ''),
        ('EffectiveDate', ''),
        ('MedicareClaimNumber', ''),
        ('SpousesName', ''),
        ('ChildsName', ''),
        ('SpousesSSN', ''),
        ('ChildsSSN', ''),
        ('ChildsDOB', ''),
        ('SpousesDOB', ''),
        ('DateChildBecameYourDependent', ''),
        ('DateOfMarriage', ''),
        ('SpouseAddressAndTelephoneNumber', ''),
        ('ExpensesPaifByDependentCHild', ''),
        ('DateOfRetirement', ''),
        ('CompanyName', ''),
        ('CompleteAddress', ''),
        ('CompletePhoneNumber', ''),
        ('Section7_Veteran_Q1', ''),
        ('Section7_Spouse_Q1', ''),
        ('Section7_Child_Q1', ''),
        ('Section7_Veteran_Q2', ''),
        ('Section7_Spouse_Q2', ''),
        ('Section7_Child_Q2', ''),
        ('Section7_Veteran_Q3', ''),
        ('Section7_Spouse_Q3', ''),
        ('Section7_Child_Q3', ''),
        ('Section8_Q1', ''),
        ('Section8_Q2', ''),
        ('Section8_Q3', ''),
        ('DateSigned', ''),
        ('SignatureOfApplicant', '')]
        )

    try:
        # Initialize processor with your fillable PDF
        processor = PDFProcessor("Form-10-10EZ.pdf")

        # Get and print all available fields
        print("Available form fields:")
        fields = processor.get_form_fields()
        from pprint import pprint

        pprint(fields)

        # Fill the form and save
        # Delete the filled_form.pdf if it already exists
        if os.path.exists("filled_form.pdf"):
            os.remove("filled_form.pdf")
        processor.fill_form(data, "filled_form.pdf")
        print("\nForm has been filled and saved as 'filled_form.pdf'")

        # Optional: Convert to images and extract text
        # image_paths = processor.convert_to_images()
        # print(f"\nConverted PDF to images: {image_paths}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")
