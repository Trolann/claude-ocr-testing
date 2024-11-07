from typing import List, Dict, Any, Tuple, Optional, Set
from dataclasses import dataclass
from pathlib import Path
import itertools
import json
import logging
from datetime import datetime
import anthropic
import Levenshtein
from enum import Enum
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import base64
import io

# I'm doing AI test validation for the Claude API related to image OCR for a form.
# I need a python script which does the following:
# 1) Takes in a list of distortions/context models for each image being passed
# 2) Takes in a directory of base images (input model)
# 3) For each image, determines all possible combinations of distortions to apply
# 4) For each distortion, it calls Claude with instructions to extract the results
#    and return in JSON format
# 5) It additionally calls Claude once with the base image and no distortions to
#     get the 'true' values
# 6) It uses Levenstein values to determine the accuracy of the results
# 6a) Optionally, for a given Levenstein value, if below the value, call Claude
#     with both outputs in json format and ask it to provide the results.
# 7) Log all results in order to use python to show statistics. Results will be
#    in one of two buckets: correct or incorrect, and a categorization on why it
#    was incorrect (hallucination/made stuff up, partially incorrect or didn't extract anything.

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename=f'ocr_validation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log',
)


class ErrorCategory(Enum):
    """Enumeration for categorizing OCR errors"""

    CORRECT = "correct"
    HALLUCINATION = "hallucination"
    PARTIAL_INCORRECT = "partial_incorrect"
    NO_EXTRACTION = "no_extraction"


@dataclass
class ValidationResult:
    """Data class to store validation results"""

    image_name: str
    distortions: List[str]
    true_json: Dict[str, Any]
    extracted_json: Dict[str, Any]
    levenshtein_distance: float
    error_category: ErrorCategory
    claude_analysis: Optional[str] = None


class OCRValidator:
    def __init__(
        self,
        api_key: str,
        base_image_dir: Path,
        distortion_list: List[str],
        levenshtein_threshold: float = 0.8,
        perform_claude_analysis: bool = True,
    ):
        """
        Initialize the OCR validator

        Args:
            api_key: Anthropic API key
            base_image_dir: Directory containing base images
            distortion_list: List of possible distortions to apply
            levenshtein_threshold: Threshold for determining if Claude analysis is needed
            perform_claude_analysis: Whether to perform additional Claude analysis on mismatches
        """
        self.client = anthropic.Client(api_key=api_key)
        self.base_image_dir = Path(base_image_dir)
        self.distortion_list = distortion_list
        self.levenshtein_threshold = levenshtein_threshold
        self.perform_claude_analysis = perform_claude_analysis
        self.results: List[ValidationResult] = []

    def encode_image(self, image_path: Path) -> str:
        """Convert image to base64 string"""
        with Image.open(image_path) as img:
            buffered = io.BytesIO()
            img.save(buffered, format=img.format)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def apply_distortions(self, image_path: Path, distortions: List[str]) -> str:
        """
        Apply specified distortions to an image
        Note: This is a placeholder - implement actual distortion logic based on your needs
        """
        # TODO: Implement actual distortion logic
        return self.encode_image(image_path)

    def get_claude_extraction(
        self, image_base64: str, system_prompt: str
    ) -> Dict[str, Any]:
        """
        Get OCR extraction from Claude for a given image

        Args:
            image_base64: Base64 encoded image
            system_prompt: Instructions for Claude on how to process the image

        Returns:
            Dictionary containing extracted information
        """
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": system_prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64,
                                },
                            },
                        ],
                    }
                ],
            )
            return json.loads(response.content[0].text)
        except Exception as e:
            logging.error(f"Error in Claude extraction: {str(e)}")
            return {}

    def compare_results(
        self, true_json: Dict[str, Any], extracted_json: Dict[str, Any]
    ) -> Tuple[float, ErrorCategory]:
        """
        Compare true and extracted JSON results

        Returns:
            Tuple of (Levenshtein distance, error category)
        """
        if not extracted_json:
            return 0.0, ErrorCategory.NO_EXTRACTION

        # Convert both JSONs to strings for comparison
        true_str = json.dumps(true_json, sort_keys=True)
        extracted_str = json.dumps(extracted_json, sort_keys=True)

        # Calculate Levenshtein distance
        distance = Levenshtein.ratio(true_str, extracted_str)

        # Categorize error
        if distance == 1.0:
            return distance, ErrorCategory.CORRECT
        elif distance < 0.3:
            return distance, ErrorCategory.HALLUCINATION
        else:
            return distance, ErrorCategory.PARTIAL_INCORRECT

    def get_claude_analysis(
        self, true_json: Dict[str, Any], extracted_json: Dict[str, Any]
    ) -> str:
        """
        Get Claude's analysis of differences between true and extracted JSON
        """
        prompt = f"""
        Compare these two JSON outputs and explain the differences:
        True values: {json.dumps(true_json, indent=2)}
        Extracted values: {json.dumps(extracted_json, indent=2)}
        
        Please provide a detailed analysis of the differences and potential reasons for the discrepancies.
        """

        response = self.client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def validate_image(self, image_path: Path) -> List[ValidationResult]:
        """
        Validate a single image with all possible distortion combinations
        """
        results = []

        # Get base truth first
        base_image = self.encode_image(image_path)
        true_json = self.get_claude_extraction(
            base_image, "Extract form fields and return as JSON"
        )

        # Generate all possible distortion combinations
        for r in range(len(self.distortion_list) + 1):
            for distortions in itertools.combinations(self.distortion_list, r):
                if (
                    not distortions
                ):  # Skip empty distortion set (already handled as base truth)
                    continue

                # Apply distortions and get extraction
                distorted_image = self.apply_distortions(image_path, list(distortions))
                extracted_json = self.get_claude_extraction(
                    distorted_image, "Extract form fields and return as JSON"
                )

                # Compare results
                distance, error_category = self.compare_results(
                    true_json, extracted_json
                )

                # Get Claude analysis if needed
                claude_analysis = None
                if (
                    self.perform_claude_analysis
                    and distance < self.levenshtein_threshold
                ):
                    claude_analysis = self.get_claude_analysis(
                        true_json, extracted_json
                    )

                # Store results
                result = ValidationResult(
                    image_name=image_path.name,
                    distortions=list(distortions),
                    true_json=true_json,
                    extracted_json=extracted_json,
                    levenshtein_distance=distance,
                    error_category=error_category,
                    claude_analysis=claude_analysis,
                )
                results.append(result)

                # Log results
                logging.info(
                    f"Processed {image_path.name} with distortions {distortions}"
                )
                logging.info(f"Error category: {error_category}, Distance: {distance}")

        return results

    def run_validation(self, max_workers: int = 4) -> pd.DataFrame:
        """
        Run validation on all images in the directory

        Args:
            max_workers: Maximum number of parallel workers

        Returns:
            DataFrame with validation statistics
        """
        image_paths = list(self.base_image_dir.glob("*.jpg")) + list(
            self.base_image_dir.glob("*.png")
        )

        # Process images in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            all_results = list(executor.map(self.validate_image, image_paths))

        # Flatten results
        self.results = [result for sublist in all_results for result in sublist]

        # Create DataFrame for analysis
        df = pd.DataFrame(
            [
                {
                    "image_name": r.image_name,
                    "distortions": ",".join(r.distortions),
                    "levenshtein_distance": r.levenshtein_distance,
                    "error_category": r.error_category.value,
                    "has_claude_analysis": bool(r.claude_analysis),
                }
                for r in self.results
            ]
        )

        # Generate and log statistics
        stats = {
            "total_tests": len(df),
            "correct": len(df[df.error_category == ErrorCategory.CORRECT.value]),
            "hallucinations": len(
                df[df.error_category == ErrorCategory.HALLUCINATION.value]
            ),
            "partial_incorrect": len(
                df[df.error_category == ErrorCategory.PARTIAL_INCORRECT.value]
            ),
            "no_extraction": len(
                df[df.error_category == ErrorCategory.NO_EXTRACTION.value]
            ),
            "average_levenshtein": df.levenshtein_distance.mean(),
        }

        logging.info("Validation Statistics:")
        logging.info(json.dumps(stats, indent=2))

        return df


def main():
    """Example usage of the OCRValidator"""
    validator = OCRValidator(
        api_key="your-api-key",
        base_image_dir=Path("./images"),
        distortion_list=["blur", "noise", "rotation", "compression"],
        levenshtein_threshold=0.8,
        perform_claude_analysis=True,
    )

    results_df = validator.run_validation()

    # Save results to CSV
    results_df.to_csv(
        f"validation_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        index=False,
    )


if __name__ == "__main__":
    main()
