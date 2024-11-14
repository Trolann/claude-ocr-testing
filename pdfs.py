import pdfrw
import pdf2image
import pytesseract
from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject, TextStringObject
import os
from collections import OrderedDict


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
        # First fill using pdfrw for text fields
        template = self.template_pdf

        # Create a mapping of encoded field names for lookup
        encoded_data = {}
        for page in template.pages:
            if page.Annots:
                for annotation in page.Annots:
                    if annotation.T:
                        encoded_name = str(annotation.T)
                        decoded_name = self.decode_pdf_field_name(encoded_name)
                        if decoded_name in data_dict:
                            encoded_data[encoded_name] = data_dict[decoded_name]

        # Fill in the fields using encoded names
        for page in template.pages:
            if page.Annots:
                for annotation in page.Annots:
                    if annotation.T and str(annotation.T) in encoded_data:
                        value = encoded_data[str(annotation.T)]

                        if not self.is_checkbox(annotation):
                            annotation.update(pdfrw.PdfDict(
                                V=value,
                                DV=value,
                                AP=''
                            ))

        # Write intermediate PDF
        writer = pdfrw.PdfWriter()
        writer.write(output_path, template)

        # Now handle checkboxes using pypdf
        reader = PdfReader(output_path)
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # Get form fields
        if '/AcroForm' in reader.trailer:
            writer.add_form_fields()

        form = reader.get_form_text_fields()

        # Update each form field
        for page in reader.pages:
            if '/Annots' in page:
                for annot in page['/Annots']:
                    if annot is None:
                        continue

                    writer_annot = annot.get_object()
                    field_name = writer_annot.get('/T', '')

                    if field_name in data_dict:
                        field_value = data_dict[field_name]
                        field_type = writer_annot.get('/FT', '')

                        if field_type == '/Btn':  # Checkbox
                            if isinstance(field_value, bool):
                                checkbox_value = field_value
                            else:
                                checkbox_value = field_value in ['Yes', 'On', True, '/1', '/Yes', 1]

                            if checkbox_value:
                                writer_annot.update({
                                    NameObject("/V"): NameObject("/Yes"),
                                    NameObject("/AS"): NameObject("/Yes"),
                                    NameObject("/DV"): NameObject("/Yes")
                                })
                            else:
                                writer_annot.update({
                                    NameObject("/V"): NameObject("/Off"),
                                    NameObject("/AS"): NameObject("/Off"),
                                    NameObject("/DV"): NameObject("/Off")
                                })
                        elif field_type == '/Tx':  # Text field
                            writer_annot.update({
                                NameObject("/V"): TextStringObject(str(field_value)),
                                NameObject("/DV"): TextStringObject(str(field_value))
                            })

        # Save the final PDF with both text fields and checkboxes
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