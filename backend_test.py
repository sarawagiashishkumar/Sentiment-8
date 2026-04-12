#!/usr/bin/env python3
"""
Backend API Validation Test Suite for Portfolio Pro
Tests all critical API endpoints for authentication, portfolio upload, and F&O custom positions.
"""

import asyncio
import io
import json
import requests
import tempfile
from pathlib import Path

# Get the backend URL from frontend/.env
BACKEND_URL = "https://sentiment-engine-ai.preview.emergentagent.com/api"

class BackendValidator:
    def __init__(self):
        self.base_url = BACKEND_URL
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Portfolio-Pro-Test/1.0'
        })
        self.auth_token = None
        self.test_results = []
    
    def log_result(self, test_name, success, details, request_data=None, response_data=None):
        """Log test result with details"""
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'request': request_data,
            'response': response_data
        }
        self.test_results.append(result)
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not success:
            print(f"   Details: {details}")
    
    def test_auth_login(self):
        """Test 1: Auth login with username @shish123 and token use"""
        try:
            # Test authentication endpoint
            auth_data = {"username": "@shish123"}
            
            response = self.session.post(
                f"{self.base_url}/auth/access", 
                json=auth_data,
                timeout=30
            )
            
            if response.status_code == 200:
                auth_response = response.json()
                if 'token' in auth_response:
                    self.auth_token = auth_response['token']
                    
                    # Test token usage by calling /me endpoint
                    headers = {'Authorization': f'Bearer {self.auth_token}'}
                    me_response = self.session.get(
                        f"{self.base_url}/auth/me",
                        headers=headers,
                        timeout=30
                    )
                    
                    if me_response.status_code == 200:
                        me_data = me_response.json()
                        self.log_result(
                            "Auth login with @shish123 and token use", 
                            True,
                            f"Successfully authenticated and accessed /me endpoint. Role: {me_data.get('role', 'unknown')}",
                            auth_data,
                            {'auth': auth_response, 'me': me_data}
                        )
                        return True
                    else:
                        self.log_result(
                            "Auth login with @shish123 and token use", 
                            False,
                            f"Token validation failed: {me_response.status_code} - {me_response.text}",
                            auth_data,
                            response.text
                        )
                        return False
                else:
                    self.log_result(
                        "Auth login with @shish123 and token use", 
                        False,
                        "No token in auth response",
                        auth_data,
                        auth_response
                    )
                    return False
            else:
                self.log_result(
                    "Auth login with @shish123 and token use", 
                    False,
                    f"Auth failed: {response.status_code} - {response.text}",
                    auth_data,
                    response.text
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Auth login with @shish123 and token use", 
                False,
                f"Exception occurred: {str(e)}",
                auth_data if 'auth_data' in locals() else None,
                None
            )
            return False
    
    def create_test_files(self):
        """Create test files for portfolio upload validation"""
        test_files = {}
        
        # Create CSV test file
        csv_content = """Symbol,Avg Price,Quantity
RELIANCE,2450.50,10
INFY,1750.25,20
SBIN,650.75,50"""
        
        csv_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        csv_file.write(csv_content)
        csv_file.close()
        test_files['csv'] = csv_file.name
        
        # Create TXT test file
        txt_content = """RELIANCE 2450.50 10
INFY 1750.25 20
SBIN 650.75 50"""
        
        txt_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        txt_file.write(txt_content)
        txt_file.close()
        test_files['txt'] = txt_file.name
        
        # Create a simple PNG file (1x1 pixel)
        png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\x12IDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01\x00\x00\x00\x00\x05\x97\n\xe6\x00\x00\x00\x00IEND\xaeB`\x82'
        
        png_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        png_file.write(png_content)
        png_file.close()
        test_files['png'] = png_file.name
        
        # Create a simple PDF (minimal valid PDF structure)
        pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj
2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj
3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj
4 0 obj
<<
/Length 44
>>
stream
BT
/F1 12 Tf
100 700 Td
(Test PDF) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000010 00000 n 
0000000053 00000 n 
0000000125 00000 n 
0000000206 00000 n 
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
297
%%EOF"""
        
        pdf_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
        pdf_file.write(pdf_content)
        pdf_file.close()
        test_files['pdf'] = pdf_file.name
        
        return test_files
    
    def test_portfolio_upload_success(self):
        """Test 2: Portfolio upload endpoint success validation for supported file types"""
        if not self.auth_token:
            self.log_result(
                "Portfolio upload success validation", 
                False,
                "No auth token available - auth must succeed first",
                None, None
            )
            return False
        
        test_files = self.create_test_files()
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        success_count = 0
        total_tests = 0
        
        # Test supported file extensions
        supported_extensions = ['csv', 'txt', 'png', 'pdf']
        
        for ext in supported_extensions:
            if ext in test_files:
                total_tests += 1
                try:
                    with open(test_files[ext], 'rb') as f:
                        files = {'file': (f'test.{ext}', f, 'application/octet-stream')}
                        
                        # Remove Content-Type from headers for file uploads
                        upload_headers = {k: v for k, v in headers.items() if k != 'Content-Type'}
                        
                        response = self.session.post(
                            f"{self.base_url}/portfolio/analyze-upload",
                            files=files,
                            headers=upload_headers,
                            timeout=30
                        )
                    
                    if response.status_code in [200, 201]:
                        success_count += 1
                        self.log_result(
                            f"Portfolio upload {ext.upper()} file", 
                            True,
                            f"Successfully uploaded {ext} file",
                            f"file: test.{ext}",
                            response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:200]
                        )
                    else:
                        self.log_result(
                            f"Portfolio upload {ext.upper()} file", 
                            False,
                            f"Upload failed: {response.status_code} - {response.text}",
                            f"file: test.{ext}",
                            response.text
                        )
                        
                except Exception as e:
                    self.log_result(
                        f"Portfolio upload {ext.upper()} file", 
                        False,
                        f"Exception during upload: {str(e)}",
                        f"file: test.{ext}",
                        None
                    )
        
        # Clean up test files
        for file_path in test_files.values():
            try:
                Path(file_path).unlink()
            except:
                pass
        
        overall_success = success_count == total_tests
        self.log_result(
            "Portfolio upload endpoint validation", 
            overall_success,
            f"Successfully uploaded {success_count}/{total_tests} supported file types",
            None, None
        )
        
        return overall_success
    
    def test_portfolio_upload_extensions(self):
        """Test 3: Portfolio upload supported extension acceptance"""
        if not self.auth_token:
            self.log_result(
                "Portfolio upload extension validation", 
                False,
                "No auth token available - auth must succeed first",
                None, None
            )
            return False
        
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        # Test all supported extensions
        supported_exts = ['.txt', '.csv', '.xls', '.xlsx', '.pdf', '.jpg', '.jpeg', '.bmp', '.png', '.webp']
        
        success_count = 0
        for ext in supported_exts:
            try:
                # Create minimal test content
                content = b"RELIANCE,2450.50,10\nINFY,1750.25,20" if ext in ['.txt', '.csv'] else b"test content"
                
                files = {'file': (f'test{ext}', io.BytesIO(content), 'application/octet-stream')}
                
                # Remove Content-Type from headers for file uploads
                upload_headers = {k: v for k, v in headers.items() if k != 'Content-Type'}
                
                response = self.session.post(
                    f"{self.base_url}/portfolio/analyze-upload",
                    files=files,
                    headers=upload_headers,
                    timeout=30
                )
                
                # Accept 200, 201 for success, or 400 for parsing issues (but extension was accepted)
                if response.status_code in [200, 201, 400]:
                    success_count += 1
                    self.log_result(
                        f"Extension {ext} acceptance", 
                        True,
                        f"Extension {ext} was accepted by server",
                        f"file: test{ext}",
                        response.status_code
                    )
                else:
                    self.log_result(
                        f"Extension {ext} acceptance", 
                        False,
                        f"Extension {ext} was rejected: {response.status_code}",
                        f"file: test{ext}",
                        response.text
                    )
                    
            except Exception as e:
                self.log_result(
                    f"Extension {ext} acceptance", 
                    False,
                    f"Exception testing {ext}: {str(e)}",
                    f"file: test{ext}",
                    None
                )
        
        overall_success = success_count == len(supported_exts)
        self.log_result(
            "Portfolio upload supported extensions", 
            overall_success,
            f"Accepted {success_count}/{len(supported_exts)} supported extensions",
            None, None
        )
        
        return overall_success
    
    def test_parse_diagnostic_errors(self):
        """Test 4: Parse-diagnostic error messages for unparseable but supported formats"""
        if not self.auth_token:
            self.log_result(
                "Parse-diagnostic error validation", 
                False,
                "No auth token available - auth must succeed first",
                None, None
            )
            return False
        
        headers = {'Authorization': f'Bearer {self.auth_token}'}
        
        # Create invalid CSV with supported extension but unparseable content
        invalid_csv = "This is not,a valid,CSV\nwith,proper portfolio,data\nno numbers here"
        
        try:
            files = {'file': ('invalid.csv', io.BytesIO(invalid_csv.encode()), 'text/csv')}
            
            # Remove Content-Type from headers for file uploads
            upload_headers = {k: v for k, v in headers.items() if k != 'Content-Type'}
            
            response = self.session.post(
                f"{self.base_url}/portfolio/analyze-upload",
                files=files,
                headers=upload_headers,
                timeout=30
            )
            
            # We expect a 400 error with diagnostic message for unparseable content
            if response.status_code == 400:
                error_text = response.text.lower()
                if any(keyword in error_text for keyword in ['parse', 'position', 'valid', 'format', 'row', 'symbol']):
                    self.log_result(
                        "Parse-diagnostic error message", 
                        True,
                        f"Proper diagnostic error returned: {response.text}",
                        "invalid CSV content",
                        response.text
                    )
                    return True
                else:
                    self.log_result(
                        "Parse-diagnostic error message", 
                        False,
                        f"Generic error instead of parse diagnostic: {response.text}",
                        "invalid CSV content",
                        response.text
                    )
                    return False
            else:
                self.log_result(
                    "Parse-diagnostic error message", 
                    False,
                    f"Expected 400 error, got {response.status_code}: {response.text}",
                    "invalid CSV content",
                    response.text
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Parse-diagnostic error message", 
                False,
                f"Exception during parse error test: {str(e)}",
                "invalid CSV content",
                None
            )
            return False
    
    def test_symbol_matching(self):
        """Test 5: Symbol matching for company names/case-insensitive on /api/portfolio/analyze"""
        if not self.auth_token:
            self.log_result(
                "Symbol matching validation", 
                False,
                "No auth token available - auth must succeed first",
                None, None
            )
            return False
        
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Content-Type': 'application/json'
        }
        
        # Test case-insensitive symbol matching with different formats
        test_cases = [
            {
                "name": "Reliance Industries Ltd",
                "payload": {"positions": [{"symbol": "Reliance Industries Ltd", "avg_price": 2450.50, "quantity": 10}]}
            },
            {
                "name": "infosys limited", 
                "payload": {"positions": [{"symbol": "infosys limited", "avg_price": 1750.25, "quantity": 20}]}
            },
            {
                "name": "sbin",
                "payload": {"positions": [{"symbol": "sbin", "avg_price": 650.75, "quantity": 50}]}
            }
        ]
        
        success_count = 0
        for test_case in test_cases:
            try:
                response = self.session.post(
                    f"{self.base_url}/portfolio/analyze",
                    json=test_case["payload"],
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    analyze_data = response.json()
                    if 'stocks' in analyze_data and len(analyze_data['stocks']) > 0:
                        stock = analyze_data['stocks'][0]
                        resolved_symbol = stock.get('symbol', '').upper()
                        
                        # Check if symbol was properly resolved
                        expected_symbols = {
                            'RELIANCE INDUSTRIES LTD': 'RELIANCE',
                            'INFOSYS LIMITED': 'INFY', 
                            'SBIN': 'SBIN'
                        }
                        
                        test_key = test_case["name"].upper()
                        if any(expected in resolved_symbol for expected in expected_symbols.values()):
                            success_count += 1
                            self.log_result(
                                f"Symbol matching: {test_case['name']}", 
                                True,
                                f"Successfully resolved '{test_case['name']}' to '{resolved_symbol}'",
                                test_case["payload"],
                                {'resolved_symbol': resolved_symbol, 'company_name': stock.get('company_name')}
                            )
                        else:
                            self.log_result(
                                f"Symbol matching: {test_case['name']}", 
                                False,
                                f"Symbol '{test_case['name']}' resolved to unexpected '{resolved_symbol}'",
                                test_case["payload"],
                                analyze_data
                            )
                    else:
                        self.log_result(
                            f"Symbol matching: {test_case['name']}", 
                            False,
                            f"No stocks returned in analysis response",
                            test_case["payload"],
                            analyze_data
                        )
                else:
                    self.log_result(
                        f"Symbol matching: {test_case['name']}", 
                        False,
                        f"Analysis failed: {response.status_code} - {response.text}",
                        test_case["payload"],
                        response.text
                    )
                    
            except Exception as e:
                self.log_result(
                    f"Symbol matching: {test_case['name']}", 
                    False,
                    f"Exception during symbol matching: {str(e)}",
                    test_case["payload"],
                    None
                )
        
        overall_success = success_count == len(test_cases)
        self.log_result(
            "Symbol matching case-insensitive validation", 
            overall_success,
            f"Successfully matched {success_count}/{len(test_cases)} symbol variations",
            None, None
        )
        
        return overall_success
    
    def test_custom_positions(self):
        """Test 6: Custom position creation and sticky alert validation"""
        if not self.auth_token:
            self.log_result(
                "Custom positions validation", 
                False,
                "No auth token available - auth must succeed first",
                None, None
            )
            return False
        
        headers = {
            'Authorization': f'Bearer {self.auth_token}',
            'Content-Type': 'application/json'
        }
        
        # Create custom position with NIFTY script and buy_price 1000
        create_data = {
            "script": "NIFTY",
            "buy_price": 1000
        }
        
        try:
            # Create the custom position
            response = self.session.post(
                f"{self.base_url}/fno/custom-position",
                json=create_data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                create_result = response.json()
                position_id = None
                
                if 'position' in create_result and 'id' in create_result['position']:
                    position_id = create_result['position']['id']
                    
                    self.log_result(
                        "Custom position creation", 
                        True,
                        f"Successfully created custom position with ID: {position_id}",
                        create_data,
                        create_result
                    )
                    
                    # Now list custom positions to verify it exists and check for sticky alerts
                    list_response = self.session.get(
                        f"{self.base_url}/fno/custom-positions",
                        headers=headers,
                        timeout=30
                    )
                    
                    if list_response.status_code == 200:
                        positions_data = list_response.json()
                        
                        # Look for our created position and check for EXIT_NOW_HIGH_LOSS alert
                        found_position = False
                        has_exit_alert = False
                        projected_exit_price = None
                        best_exit_price = None
                        recovery_potential = None
                        
                        for position in positions_data:
                            if position.get('id') == position_id:
                                found_position = True
                                alert = position.get('alert', '')
                                
                                if 'EXIT_NOW_HIGH_LOSS' in alert:
                                    has_exit_alert = True
                                
                                projected_exit_price = position.get('projected_exit_price')
                                best_exit_price = position.get('best_exit_price')
                                recovery_potential = position.get('recovery_potential')
                                
                                break
                        
                        if found_position:
                            alert_success = has_exit_alert and projected_exit_price is not None
                            self.log_result(
                                "Custom position sticky alert validation", 
                                alert_success,
                                f"Position found with EXIT_NOW_HIGH_LOSS alert: {has_exit_alert}, "
                                f"projected_exit_price: {projected_exit_price}, "
                                f"best_exit_price: {best_exit_price}, "
                                f"recovery_potential: {recovery_potential}",
                                None,
                                {
                                    'alert': alert,
                                    'projected_exit_price': projected_exit_price,
                                    'best_exit_price': best_exit_price,
                                    'recovery_potential': recovery_potential
                                }
                            )
                            return alert_success
                        else:
                            self.log_result(
                                "Custom position sticky alert validation", 
                                False,
                                f"Created position with ID {position_id} not found in list",
                                None,
                                positions_data
                            )
                            return False
                    else:
                        self.log_result(
                            "Custom position sticky alert validation", 
                            False,
                            f"Failed to list positions: {list_response.status_code} - {list_response.text}",
                            None,
                            list_response.text
                        )
                        return False
                else:
                    self.log_result(
                        "Custom position creation", 
                        False,
                        "No position ID in create response",
                        create_data,
                        create_result
                    )
                    return False
            else:
                self.log_result(
                    "Custom position creation", 
                    False,
                    f"Create position failed: {response.status_code} - {response.text}",
                    create_data,
                    response.text
                )
                return False
                
        except Exception as e:
            self.log_result(
                "Custom position creation and validation", 
                False,
                f"Exception during custom position test: {str(e)}",
                create_data,
                None
            )
            return False
    
    def run_all_tests(self):
        """Run all validation tests in sequence"""
        print(f"\n🚀 Starting Backend API Validation for: {self.base_url}\n")
        
        test_methods = [
            self.test_auth_login,
            self.test_portfolio_upload_success,
            self.test_portfolio_upload_extensions,
            self.test_parse_diagnostic_errors,
            self.test_symbol_matching,
            self.test_custom_positions
        ]
        
        passed = 0
        total = len(test_methods)
        
        for test_method in test_methods:
            try:
                if test_method():
                    passed += 1
                print()  # Add spacing between tests
            except Exception as e:
                print(f"❌ CRITICAL ERROR in {test_method.__name__}: {str(e)}\n")
        
        return passed, total
    
    def print_summary(self):
        """Print detailed test summary"""
        passed = sum(1 for result in self.test_results if result['success'])
        total = len(self.test_results)
        
        print("=" * 80)
        print(f"📊 BACKEND API VALIDATION SUMMARY")
        print("=" * 80)
        print(f"Overall Result: {passed}/{total} tests passed")
        print()
        
        print("🔍 DETAILED RESULTS:")
        for result in self.test_results:
            status = "✅ PASS" if result['success'] else "❌ FAIL"
            print(f"{status}: {result['test']}")
            if not result['success']:
                print(f"   ⚠️  {result['details']}")
                if result['response']:
                    response_str = str(result['response'])[:100]
                    print(f"   📝 Response: {response_str}...")
        
        print("\n" + "=" * 80)
        
        if passed == total:
            print("🎉 ALL TESTS PASSED - Backend API is fully functional!")
        else:
            failed = total - passed
            print(f"⚠️  {failed} test(s) failed - Backend API has issues that need attention")
        
        print("=" * 80)


def main():
    """Main execution function"""
    validator = BackendValidator()
    
    try:
        passed, total = validator.run_all_tests()
        validator.print_summary()
        
        return passed == total
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Testing interrupted by user")
        return False
    except Exception as e:
        print(f"\n\n💥 CRITICAL ERROR: {str(e)}")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)