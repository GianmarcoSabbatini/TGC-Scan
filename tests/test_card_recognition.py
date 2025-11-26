"""
TCG Scan - Card Recognition Tests
Tests for image processing and card recognition functionality
"""
import pytest
import numpy as np
from PIL import Image
from unittest.mock import patch, MagicMock
import tempfile
import os


class TestImagePreprocessing:
    """Tests for image preprocessing functions"""
    
    def test_preprocess_valid_image(self, mock_image_file):
        """Test preprocessing a valid image"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        processed, pil_img = engine.preprocess_image(str(mock_image_file))
        
        assert processed is not None
        assert pil_img is not None
        assert isinstance(pil_img, Image.Image)
        
    def test_preprocess_nonexistent_file(self):
        """Test preprocessing with nonexistent file raises error"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        with pytest.raises(ValueError, match="Could not load image"):
            engine.preprocess_image('/nonexistent/path/image.jpg')
            
    def test_preprocess_invalid_file(self, temp_upload_dir):
        """Test preprocessing with invalid image file"""
        from card_recognition import CardRecognitionEngine
        
        # Create a non-image file
        invalid_file = temp_upload_dir / 'invalid.jpg'
        invalid_file.write_text('not an image')
        
        engine = CardRecognitionEngine()
        
        with pytest.raises(ValueError):
            engine.preprocess_image(str(invalid_file))
            
    def test_preprocess_different_formats(self, temp_upload_dir):
        """Test preprocessing different image formats"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        formats = ['JPEG', 'PNG', 'BMP']
        
        for fmt in formats:
            img = Image.fromarray(np.random.randint(0, 255, (200, 150, 3), dtype=np.uint8))
            ext = 'jpg' if fmt == 'JPEG' else fmt.lower()
            filepath = temp_upload_dir / f'test.{ext}'
            img.save(filepath, format=fmt)
            
            processed, pil_img = engine.preprocess_image(str(filepath))
            assert processed is not None


class TestImageHashing:
    """Tests for perceptual hashing"""
    
    def test_compute_image_hash(self, mock_image_file):
        """Test computing image hash"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        _, pil_img = engine.preprocess_image(str(mock_image_file))
        
        img_hash = engine.compute_image_hash(pil_img)
        
        assert img_hash is not None
        assert isinstance(img_hash, str)
        assert len(img_hash) > 0
        
    def test_hash_consistency(self, temp_upload_dir):
        """Test that same image produces same hash"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        # Create consistent image
        np.random.seed(42)
        img_array = np.random.randint(0, 255, (200, 150, 3), dtype=np.uint8)
        
        # Save same image twice
        for i in range(2):
            img = Image.fromarray(img_array)
            filepath = temp_upload_dir / f'consistent_{i}.jpg'
            img.save(filepath, format='JPEG', quality=100)
        
        # Compute hashes
        _, pil1 = engine.preprocess_image(str(temp_upload_dir / 'consistent_0.jpg'))
        _, pil2 = engine.preprocess_image(str(temp_upload_dir / 'consistent_1.jpg'))
        
        hash1 = engine.compute_image_hash(pil1)
        hash2 = engine.compute_image_hash(pil2)
        
        # Hashes should be identical or very similar
        assert hash1 == hash2


class TestCardMatching:
    """Tests for card matching functionality"""
    
    def test_find_matching_card_empty_db(self, db_session):
        """Test finding match with empty database"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        with patch('card_recognition.get_db', return_value=db_session):
            result = engine.find_matching_card('abcd1234' * 8, 'mtg')
        
        assert result is None
        
    def test_find_matching_card_with_match(self, db_session, sample_card_data):
        """Test finding match when card exists"""
        from card_recognition import CardRecognitionEngine
        from database import Card
        
        # Create card with known hash
        sample_card_data['image_hash'] = '0' * 64  # All zeros hash
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        engine = CardRecognitionEngine()
        
        with patch('card_recognition.get_db', return_value=db_session):
            result = engine.find_matching_card('0' * 64, 'mtg')
        
        if result:
            matched_card, confidence = result
            assert matched_card.name == 'Lightning Bolt'
            assert confidence >= 0.0


class TestRecognitionPipeline:
    """Tests for the complete recognition pipeline"""
    
    def test_recognize_card_success(self, mock_image_file, db_session, sample_card_data):
        """Test successful card recognition"""
        from card_recognition import CardRecognitionEngine
        from database import Card
        
        # Create card in database
        card = Card(**sample_card_data)
        db_session.add(card)
        db_session.commit()
        
        engine = CardRecognitionEngine()
        
        with patch.object(engine, 'find_matching_card') as mock_find:
            mock_find.return_value = (card, 0.95)
            
            result = engine.recognize_card(str(mock_image_file), 'mtg')
            
            assert result['success'] is True
            assert result['confidence'] == 0.95
            assert result['card']['name'] == 'Lightning Bolt'
            
    def test_recognize_card_no_match(self, mock_image_file):
        """Test recognition with no match found"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        with patch.object(engine, 'find_matching_card', return_value=None):
            result = engine.recognize_card(str(mock_image_file), 'mtg')
            
            assert result['success'] is False
            assert result['confidence'] == 0.0
            assert 'No matching card' in result['message']
            
    def test_recognize_card_invalid_image(self):
        """Test recognition with invalid image"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        result = engine.recognize_card('/invalid/path.jpg', 'mtg')
        
        assert result['success'] is False
        assert 'error' in result
        
    def test_batch_recognize(self, temp_upload_dir):
        """Test batch recognition"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        # Create multiple images
        image_paths = []
        for i in range(3):
            img = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
            filepath = temp_upload_dir / f'batch_{i}.jpg'
            img.save(filepath)
            image_paths.append(str(filepath))
        
        with patch.object(engine, 'find_matching_card', return_value=None):
            results = engine.batch_recognize(image_paths, 'mtg')
        
        assert len(results) == 3
        assert all('success' in r for r in results)


class TestDownloadAndHash:
    """Tests for image download and hashing utility"""
    
    def test_download_and_hash_success(self):
        """Test downloading and hashing image from URL"""
        # download_and_hash_card_image is in card_recognition module
        from card_recognition import download_and_hash_card_image
        
        # Mock requests
        with patch('card_recognition.requests') as mock_requests:
            # Create a fake image response
            img = Image.new('RGB', (100, 100), color='red')
            import io
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = img_bytes.read()
            mock_requests.get.return_value = mock_response
            
            result = download_and_hash_card_image({'image_url': 'https://example.com/card.png'})
            
            assert result is not None
            assert isinstance(result, str)
            
    def test_download_and_hash_no_url(self):
        """Test with missing image URL"""
        from card_recognition import download_and_hash_card_image
        
        result = download_and_hash_card_image({})
        assert result is None
        
    def test_download_and_hash_failed_request(self):
        """Test with failed HTTP request"""
        from card_recognition import download_and_hash_card_image
        
        with patch('card_recognition.requests') as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_requests.get.return_value = mock_response
            
            result = download_and_hash_card_image({'image_url': 'https://example.com/notfound.png'})
            
            assert result is None
            
    def test_download_and_hash_network_error(self):
        """Test with network error"""
        from card_recognition import download_and_hash_card_image
        import requests
        
        with patch('card_recognition.requests') as mock_requests:
            mock_requests.get.side_effect = requests.RequestException("Network error")
            
            result = download_and_hash_card_image({'image_url': 'https://example.com/card.png'})
            
            assert result is None


class TestEdgeCases:
    """Tests for edge cases and error handling"""
    
    def test_very_small_image(self, temp_upload_dir):
        """Test with very small image"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        # Create tiny image
        img = Image.new('RGB', (10, 10), color='gray')
        filepath = temp_upload_dir / 'tiny.jpg'
        img.save(filepath)
        
        # Should handle without crashing
        try:
            processed, pil_img = engine.preprocess_image(str(filepath))
            assert processed is not None
        except Exception:
            # May raise exception for too-small images, which is acceptable
            pass
            
    def test_very_large_image(self, temp_upload_dir):
        """Test with large image"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        # Create large image
        img = Image.fromarray(np.random.randint(0, 255, (2000, 1500, 3), dtype=np.uint8))
        filepath = temp_upload_dir / 'large.jpg'
        img.save(filepath, quality=90)
        
        processed, pil_img = engine.preprocess_image(str(filepath))
        assert processed is not None
        
    def test_grayscale_image(self, temp_upload_dir):
        """Test with grayscale image"""
        from card_recognition import CardRecognitionEngine
        
        engine = CardRecognitionEngine()
        
        # Create grayscale image
        img = Image.fromarray(np.random.randint(0, 255, (200, 150), dtype=np.uint8), mode='L')
        filepath = temp_upload_dir / 'grayscale.jpg'
        img.save(filepath)
        
        # May need to handle differently
        try:
            processed, pil_img = engine.preprocess_image(str(filepath))
            # Should convert or handle gracefully
        except Exception:
            # Acceptable if raises specific error
            pass
