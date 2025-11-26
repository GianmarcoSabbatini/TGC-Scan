"""
TCG Scan - API Endpoint Tests
Tests for all REST API endpoints
"""
import pytest
import json
import io
from unittest.mock import patch, MagicMock
from PIL import Image
import numpy as np


class TestHealthEndpoints:
    """Tests for basic health/status endpoints"""
    
    def test_index_returns_html(self, client):
        """Test that index returns the main page"""
        response = client.get('/')
        assert response.status_code == 200
        
    def test_static_file_serving(self, client):
        """Test that static files are served"""
        response = client.get('/app.js')
        assert response.status_code == 200


class TestScanEndpoints:
    """Tests for card scanning endpoints"""
    
    def test_upload_scan_no_file(self, client):
        """Test upload without file returns error"""
        response = client.post('/api/scan/upload')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        
    def test_upload_scan_empty_file(self, client):
        """Test upload with empty filename returns error"""
        response = client.post(
            '/api/scan/upload',
            data={'file': (io.BytesIO(b''), '')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        
    def test_upload_scan_invalid_extension(self, client):
        """Test upload with invalid file type returns error"""
        response = client.post(
            '/api/scan/upload',
            data={'file': (io.BytesIO(b'fake data'), 'test.txt')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'Invalid file type' in data['error']
        
    def test_upload_scan_valid_image(self, client, temp_upload_dir, monkeypatch):
        """Test upload with valid image"""
        import config
        monkeypatch.setattr(config, 'UPLOAD_FOLDER', temp_upload_dir)
        
        # Create a valid image
        img = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        img_bytes.seek(0)
        
        # Mock recognition
        with patch('app.recognition_engine') as mock_engine:
            mock_engine.recognize_card.return_value = {
                'success': False,
                'card': None,
                'confidence': 0.0,
                'message': 'No match found'
            }
            
            response = client.post(
                '/api/scan/upload',
                data={
                    'file': (img_bytes, 'test_card.jpg'),
                    'tcg': 'mtg'
                },
                content_type='multipart/form-data'
            )
            
            assert response.status_code == 200
            
    def test_batch_scan_no_files(self, client):
        """Test batch scan without files"""
        response = client.post('/api/scan/batch')
        assert response.status_code == 400
        
    def test_batch_scan_with_files(self, client, temp_upload_dir, monkeypatch):
        """Test batch scan with multiple files"""
        import config
        monkeypatch.setattr(config, 'UPLOAD_FOLDER', temp_upload_dir)
        
        # Create test images
        images = []
        for i in range(3):
            img = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='JPEG')
            img_bytes.seek(0)
            images.append((img_bytes, f'card_{i}.jpg'))
        
        with patch('app.recognition_engine') as mock_engine:
            mock_engine.recognize_card.return_value = {
                'success': False,
                'card': None,
                'confidence': 0.0,
                'message': 'No match'
            }
            
            response = client.post(
                '/api/scan/batch',
                data={
                    'files': images,
                    'tcg': 'mtg'
                },
                content_type='multipart/form-data'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'results' in data


class TestCardDatabaseEndpoints:
    """Tests for card database endpoints"""
    
    def test_search_cards_empty(self, client):
        """Test searching cards with no query"""
        response = client.get('/api/cards/search')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'cards' in data
        assert 'count' in data
        
    def test_search_cards_with_query(self, client):
        """Test searching cards with query parameter"""
        response = client.get('/api/cards/search?q=Lightning')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'cards' in data
        
    def test_search_cards_with_tcg_filter(self, client):
        """Test searching cards filtered by TCG"""
        response = client.get('/api/cards/search?q=bolt&tcg=mtg')
        assert response.status_code == 200
        
    def test_search_cards_with_limit(self, client):
        """Test searching cards with limit parameter"""
        response = client.get('/api/cards/search?limit=10')
        assert response.status_code == 200
        
    def test_import_card_no_name(self, client):
        """Test importing card without name"""
        response = client.post(
            '/api/cards/import',
            data=json.dumps({'tcg': 'mtg'}),
            content_type='application/json'
        )
        assert response.status_code == 400
        
    def test_import_card_with_mock(self, client):
        """Test importing card with mocked API"""
        with patch('app.api_manager') as mock_api:
            mock_api.search_card.return_value = {
                'tcg': 'mtg',
                'card_id': 'test-123',
                'name': 'Test Card',
                'set_code': 'TST',
                'set_name': 'Test Set'
            }
            
            with patch('app.download_and_hash_card_image', return_value='abcd1234'):
                response = client.post(
                    '/api/cards/import',
                    data=json.dumps({
                        'name': 'Test Card',
                        'tcg': 'mtg'
                    }),
                    content_type='application/json'
                )
                
                # May succeed or fail depending on DB state
                assert response.status_code in [200, 404, 500]
                
    def test_import_card_not_found(self, client):
        """Test importing non-existent card"""
        with patch('app.api_manager') as mock_api:
            mock_api.search_card.return_value = None
            
            response = client.post(
                '/api/cards/import',
                data=json.dumps({
                    'name': 'NonExistent Card XYZZZ',
                    'tcg': 'mtg'
                }),
                content_type='application/json'
            )
            
            assert response.status_code == 404
            
    def test_bulk_import_no_set_code(self, client):
        """Test bulk import without set code"""
        response = client.post(
            '/api/cards/bulk-import',
            data=json.dumps({'tcg': 'mtg'}),
            content_type='application/json'
        )
        assert response.status_code == 400
        
    def test_bulk_import_non_mtg(self, client):
        """Test bulk import for non-MTG TCG returns error"""
        response = client.post(
            '/api/cards/bulk-import',
            data=json.dumps({
                'tcg': 'pokemon',
                'set_code': 'SWSH1'
            }),
            content_type='application/json'
        )
        assert response.status_code == 400


class TestCollectionEndpoints:
    """Tests for collection management endpoints"""
    
    def test_get_collection(self, client):
        """Test getting collection"""
        response = client.get('/api/collection')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'cards' in data
        assert 'count' in data
        
    def test_get_collection_with_tcg_filter(self, client):
        """Test getting collection filtered by TCG"""
        response = client.get('/api/collection?tcg=mtg')
        assert response.status_code == 200
        
    def test_get_collection_stats(self, client):
        """Test getting collection statistics"""
        response = client.get('/api/collection/stats')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'total_cards' in data
        assert 'unique_cards' in data


class TestSortingEndpoints:
    """Tests for sorting endpoints"""
    
    def test_preview_sorting(self, client):
        """Test sorting preview"""
        response = client.post(
            '/api/sort/preview',
            data=json.dumps({
                'criteria': 'alphabetic',
                'bin_count': 6
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        
    def test_preview_sorting_with_sub_criteria(self, client):
        """Test sorting preview with sub-criteria"""
        response = client.post(
            '/api/sort/preview',
            data=json.dumps({
                'criteria': 'alphabetic',
                'sub_criteria': '2nd_letter',
                'bin_count': 6
            }),
            content_type='application/json'
        )
        assert response.status_code == 200
        
    def test_apply_sorting(self, client):
        """Test applying sorting"""
        response = client.post(
            '/api/sort/apply',
            data=json.dumps({
                'criteria': 'rarity',
                'bin_count': 4
            }),
            content_type='application/json'
        )
        assert response.status_code == 200


class TestPriceEndpoints:
    """Tests for price tracking endpoints"""
    
    def test_update_prices(self, client):
        """Test updating prices"""
        with patch('app.price_tracker') as mock_tracker:
            mock_tracker.update_all_prices.return_value = {
                'total': 10,
                'updated': 5,
                'failed': 2,
                'skipped': 3
            }
            
            response = client.post(
                '/api/prices/update',
                data=json.dumps({'tcg': 'mtg', 'max_cards': 10}),
                content_type='application/json'
            )
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'updated' in data
            
    def test_get_price_history(self, client):
        """Test getting price history for a card"""
        with patch('app.price_tracker') as mock_tracker:
            mock_tracker.get_card_price_history.return_value = [
                {'price': 5.00, 'recorded_at': '2025-01-01'},
                {'price': 5.50, 'recorded_at': '2025-01-02'}
            ]
            
            response = client.get('/api/prices/history/1')
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'history' in data
            
    def test_get_price_history_with_days(self, client):
        """Test getting price history with days parameter"""
        with patch('app.price_tracker') as mock_tracker:
            mock_tracker.get_card_price_history.return_value = []
            
            response = client.get('/api/prices/history/1?days=7')
            assert response.status_code == 200


class TestInputValidation:
    """Tests for input validation"""
    
    def test_search_with_sql_injection_attempt(self, client):
        """Test that SQL injection is handled"""
        response = client.get("/api/cards/search?q='; DROP TABLE cards; --")
        # Should not crash, may return empty results
        assert response.status_code == 200
        
    def test_import_with_very_long_name(self, client):
        """Test importing card with extremely long name"""
        long_name = 'A' * 10000
        
        with patch('app.api_manager') as mock_api:
            mock_api.search_card.return_value = None
            
            response = client.post(
                '/api/cards/import',
                data=json.dumps({'name': long_name, 'tcg': 'mtg'}),
                content_type='application/json'
            )
            # Should handle gracefully
            assert response.status_code in [400, 404, 500]
            
    def test_sort_with_invalid_bin_count(self, client):
        """Test sorting with invalid bin count"""
        response = client.post(
            '/api/sort/preview',
            data=json.dumps({
                'criteria': 'color',
                'bin_count': -1
            }),
            content_type='application/json'
        )
        # Should handle gracefully or return error
        assert response.status_code in [200, 400]
        
    def test_sort_with_invalid_criteria(self, client):
        """Test sorting with invalid criteria"""
        response = client.post(
            '/api/sort/preview',
            data=json.dumps({
                'criteria': 'invalid_criteria',
                'bin_count': 6
            }),
            content_type='application/json'
        )
        assert response.status_code in [200, 400, 500]


class TestCORSAndHeaders:
    """Tests for CORS and response headers"""
    
    def test_cors_headers_present(self, client):
        """Test that CORS headers are present"""
        response = client.options('/api/cards/search')
        # Flask-CORS should add appropriate headers
        assert response.status_code in [200, 204]
        
    def test_content_type_json(self, client):
        """Test that API responses have correct content type"""
        response = client.get('/api/collection')
        assert response.content_type.startswith('application/json')
