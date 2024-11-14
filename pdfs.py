from pypdf import PdfReader, PdfWriter
import pdf2image
import pytesseract
from pdf2image import convert_from_path
import os
from collections import OrderedDict


class PDFProcessor:
    def __init__(self, input_pdf_path):
        """Initialize with path to fillable PDF form."""
        self.input_pdf_path = input_pdf_path
        self.reader = PdfReader(input_pdf_path)

    def is_checkbox(self, field):
        """
        Determine if a form field is a checkbox.
        """
        return field.field_type == "/Btn"

    def fill_form(self, data_dict, output_path):
        """
        Fill PDF form with given data and save to output_path.

        Args:
            data_dict (dict): Dictionary with field names as keys
            output_path (str): Path where to save the filled PDF
        """
        writer = PdfWriter()
        
        # Copy all pages from the template
        for page in self.reader.pages:
            writer.add_page(page)
            
        # Get the form fields from the template
        writer.update_page_form_field_values(
            writer.pages[0],  # Update fields on first page
            data_dict
        )
        
        # Write the filled form to the output path
        with open(output_path, "wb") as output_file:
            writer.write(output_file)


    def get_form_fields(self):
        """Return an ordered dictionary of all fillable form fields."""
        try:
            fields = self.reader.get_form_text_fields()
            return OrderedDict(fields) if fields else OrderedDict()
        except Exception:
            return OrderedDict()

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
        ('TypeOfBenefitsApplyingFor', '/1'),
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
        #pprint(fields)

        # Fill the form and save
        processor.fill_form(data, "filled_form.pdf")
        print("\nForm has been filled and saved as 'filled_form.pdf'")

        # Optional: Convert to images and extract text
        image_paths = processor.convert_to_images()
        print(f"\nConverted PDF to images: {image_paths}")


    except Exception as e:
        print(f"An error occurred: {str(e)}")


