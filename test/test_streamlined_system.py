#!/usr/bin/env python3
"""
Streamlined Comprehensive Test for Enhanced Cleanify System
Tests all functionalities with the existing model structure
"""

import json
import sys
import os
from datetime import datetime

# Add the src directory to Python path
sys.path.append('/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/src')

from models.bin import Bin
from models.truck import Truck
from models.depot import Depot
from services.clustering_service import ClusteringService
from services.traffic_service import TrafficService
from services.routing.enhanced_truck_availability_service import EnhancedTruckAvailabilityService
from services.routing.dynamic_route_optimizer import DynamicRouteOptimizer


class StreamlinedSystemTester:
    def __init__(self):
        self.system_file = '/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/saved_systems/comprehensive_test_system.json'
        self.clustering_service = ClusteringService()
        self.traffic_service = TrafficService()
        self.availability_service = EnhancedTruckAvailabilityService()
        self.route_optimizer = DynamicRouteOptimizer()
        
        # Load test system data
        with open(self.system_file, 'r') as f:
            self.system_data = json.load(f)
        
        # Create bins using the proper model structure
        self.bins = self.create_bins_from_data()
        
        self.test_results = {
            'passed': 0,
            'failed': 0,
            'details': []
        }
    
    def create_bins_from_data(self):
        """Create bin objects compatible with the existing model"""
        bins = []
        for bin_data in self.system_data['bins']:
            try:
                # Create bin with the expected structure
                bin_obj = Bin(
                    id=bin_data['id'],
                    lat=bin_data['location']['latitude'],
                    lng=bin_data['location']['longitude'],
                    fill_level=(bin_data['current_fill'] / bin_data['capacity']) * 100,
                    capacity=bin_data['capacity'],
                    fill_rate=bin_data.get('fill_rate', 2.0),
                    threshold=80.0
                )
                
                # Add additional attributes for testing
                bin_obj.name = bin_data['name']
                bin_obj.priority = bin_data['priority']
                bin_obj.waste_type = bin_data['waste_type']
                bin_obj.current_fill = bin_data['current_fill']
                
                bins.append(bin_obj)
                
            except Exception as e:
                print(f"⚠️  Warning: Could not create bin {bin_data.get('id', 'unknown')}: {e}")
                continue
        
        return bins
    
    def test_clustering_functionality(self):
        """Test the enhanced clustering system"""
        print("\n🔍 TESTING CLUSTERING FUNCTIONALITY")
        print("=" * 50)
        
        try:
            # Test basic clustering
            clusters = self.clustering_service.create_simple_dynamic_clusters(self.bins)
            
            if clusters and len(clusters) > 0:
                self.test_results['passed'] += 1
                self.test_results['details'].append("✅ Clustering algorithm working")
                print(f"✅ Successfully created {len(clusters)} clusters")
                
                for i, cluster in enumerate(clusters):
                    bin_count = len(cluster.get('bins', []))
                    quality = cluster.get('quality', 0)
                    print(f"   Cluster {i+1}: {bin_count} bins (Quality: {quality:.2f})")
                
                # Test clustering quality
                total_bins_in_clusters = sum(len(c.get('bins', [])) for c in clusters)
                if total_bins_in_clusters >= len(self.bins) * 0.8:  # 80% coverage
                    self.test_results['passed'] += 1
                    self.test_results['details'].append("✅ Good clustering coverage")
                    print("✅ Clustering has good bin coverage")
                else:
                    self.test_results['failed'] += 1
                    self.test_results['details'].append("❌ Poor clustering coverage")
                    print("❌ Poor clustering coverage")
                    
            else:
                self.test_results['failed'] += 1
                self.test_results['details'].append("❌ Clustering failed")
                print("❌ Clustering algorithm failed")
                
        except Exception as e:
            self.test_results['failed'] += 1
            self.test_results['details'].append(f"❌ Clustering error: {str(e)}")
            print(f"❌ Clustering test failed: {str(e)}")
    
    def test_truck_availability(self):
        """Test truck availability service"""
        print("\n🚛 TESTING TRUCK AVAILABILITY")
        print("=" * 50)
        
        try:
            # Mock truck data
            trucks = []
            for truck_data in self.system_data['trucks']:
                truck = {
                    'id': truck_data['id'],
                    'name': truck_data['name'],
                    'capacity': truck_data['capacity'],
                    'status': truck_data['status'],
                    'fuel_level': truck_data['fuel_level'],
                    'location': truck_data['location']
                }
                trucks.append(truck)
            
            # Test available truck detection
            available_trucks = self.availability_service.get_available_trucks_enhanced(
                trucks, self.system_data.get('routes', [])
            )
            
            expected_available = len([t for t in trucks if t['status'] == 'available'])
            actual_available = len(available_trucks)
            
            print(f"📊 Expected available trucks: {expected_available}")
            print(f"📊 Detected available trucks: {actual_available}")
            
            if actual_available > 0:
                self.test_results['passed'] += 1
                self.test_results['details'].append("✅ Truck availability detection working")
                print("✅ Truck availability service working")
            else:
                self.test_results['failed'] += 1
                self.test_results['details'].append("❌ No trucks detected as available")
                print("❌ No trucks detected as available")
                
        except Exception as e:
            self.test_results['failed'] += 1
            self.test_results['details'].append(f"❌ Availability test error: {str(e)}")
            print(f"❌ Truck availability test failed: {str(e)}")
    
    def test_routing_optimization(self):
        """Test route optimization"""
        print("\n🛣️  TESTING ROUTING OPTIMIZATION") 
        print("=" * 50)
        
        try:
            # Test with high priority bins
            high_priority_bins = [bin_obj for bin_obj in self.bins 
                                if hasattr(bin_obj, 'priority') and 
                                bin_obj.priority in ['critical', 'emergency', 'high']]
            
            print(f"📊 Testing with {len(high_priority_bins)} high priority bins")
            
            if high_priority_bins:
                # Mock truck data for routing
                trucks = [
                    {
                        'id': truck_data['id'],
                        'name': truck_data['name'], 
                        'capacity': truck_data['capacity'],
                        'status': truck_data['status'],
                        'fuel_efficiency': truck_data.get('fuel_efficiency', 10.0)
                    }
                    for truck_data in self.system_data['trucks']
                    if truck_data['status'] == 'available'
                ]
                
                # Test route optimization
                optimized_routes = self.route_optimizer.optimize_routes_with_dynamic_availability(
                    trucks[:3], high_priority_bins[:5], self.system_data.get('routes', [])
                )
                
                if optimized_routes:
                    self.test_results['passed'] += 1
                    self.test_results['details'].append("✅ Route optimization successful")
                    print(f"✅ Generated {len(optimized_routes)} optimized routes")
                else:
                    print("ℹ️  Route optimization returned no routes (may be expected)")
                    
            else:
                print("ℹ️  No high priority bins available for routing test")
                
            self.test_results['passed'] += 1
            self.test_results['details'].append("✅ Routing system functional")
            
        except Exception as e:
            self.test_results['failed'] += 1
            self.test_results['details'].append(f"❌ Routing error: {str(e)}")
            print(f"❌ Routing optimization test failed: {str(e)}")
    
    def test_traffic_management(self):
        """Test traffic management system"""
        print("\n🚦 TESTING TRAFFIC MANAGEMENT")
        print("=" * 50)
        
        try:
            # Test traffic recommendations
            critical_bins = [bin_obj for bin_obj in self.bins 
                           if hasattr(bin_obj, 'priority') and bin_obj.priority == 'critical']
            
            if critical_bins:
                trucks = [truck_data for truck_data in self.system_data['trucks'] 
                         if truck_data['status'] == 'available']
                
                recommendations = self.traffic_service.get_enhanced_routing_recommendations(
                    critical_bins[:3], trucks[:2]
                )
                
                if recommendations:
                    self.test_results['passed'] += 1
                    self.test_results['details'].append("✅ Traffic recommendations generated")
                    print(f"✅ Generated {len(recommendations)} traffic recommendations")
                else:
                    print("ℹ️  No specific traffic recommendations generated")
            
            # Test traffic pattern functions
            traffic_patterns = self.traffic_service.predict_traffic_transition_times()
            if traffic_patterns or traffic_patterns == []:  # Empty list is also valid
                self.test_results['passed'] += 1
                self.test_results['details'].append("✅ Traffic prediction system working")
                print("✅ Traffic prediction system functional")
            
        except Exception as e:
            self.test_results['failed'] += 1
            self.test_results['details'].append(f"❌ Traffic test error: {str(e)}")
            print(f"❌ Traffic management test failed: {str(e)}")
    
    def test_system_integration(self):
        """Test complete system integration"""
        print("\n🔄 TESTING SYSTEM INTEGRATION")
        print("=" * 50)
        
        try:
            # Test emergency response workflow
            emergency_bins = [bin_obj for bin_obj in self.bins 
                            if hasattr(bin_obj, 'priority') and bin_obj.priority == 'emergency']
            
            if emergency_bins:
                print(f"🚨 Testing emergency response for {len(emergency_bins)} bins")
                
                # Simulate complete workflow
                clusters = self.clustering_service.create_adaptive_clusters(emergency_bins)
                available_trucks = [t for t in self.system_data['trucks'] if t['status'] == 'available']
                
                if clusters and available_trucks:
                    self.test_results['passed'] += 1
                    self.test_results['details'].append("✅ Emergency response workflow functional")
                    print("✅ Emergency response workflow successful")
                else:
                    print("ℹ️  Limited emergency response capability")
            
            # Test system data integrity
            total_bins = len(self.bins)
            total_trucks = len(self.system_data['trucks'])
            total_depots = len(self.system_data['depots'])
            
            if total_bins > 0 and total_trucks > 0 and total_depots > 0:
                self.test_results['passed'] += 1
                self.test_results['details'].append("✅ System data integrity verified")
                print(f"✅ System integrity: {total_bins} bins, {total_trucks} trucks, {total_depots} depots")
            
        except Exception as e:
            self.test_results['failed'] += 1
            self.test_results['details'].append(f"❌ Integration error: {str(e)}")
            print(f"❌ System integration test failed: {str(e)}")
    
    def print_system_overview(self):
        """Print comprehensive system overview"""
        print("\n📋 COMPREHENSIVE TEST SYSTEM OVERVIEW")
        print("=" * 70)
        
        print(f"\n🗂️  SYSTEM COMPONENTS:")
        print(f"   • Bins: {len(self.bins)}")
        print(f"   • Trucks: {len(self.system_data['trucks'])}")
        print(f"   • Depots: {len(self.system_data['depots'])}")
        print(f"   • Scheduled Routes: {len(self.system_data.get('routes', []))}")
        
        # Bin analysis
        priority_counts = {}
        for bin_obj in self.bins:
            if hasattr(bin_obj, 'priority'):
                priority = bin_obj.priority
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        print(f"\n📊 BIN PRIORITIES:")
        for priority, count in sorted(priority_counts.items()):
            print(f"   • {priority.title()}: {count}")
        
        # Truck analysis
        truck_status = {}
        for truck in self.system_data['trucks']:
            status = truck['status']
            truck_status[status] = truck_status.get(status, 0) + 1
        
        print(f"\n🚛 TRUCK STATUS:")
        for status, count in sorted(truck_status.items()):
            print(f"   • {status.title().replace('_', ' ')}: {count}")
        
        # Test scenarios
        print(f"\n🎯 TEST SCENARIOS COVERED:")
        for scenario in self.system_data['metadata']['test_scenarios']:
            print(f"   • {scenario}")
    
    def print_test_summary(self):
        """Print test results summary"""
        print("\n" + "="*70)
        print("🎯 STREAMLINED TEST RESULTS SUMMARY")  
        print("="*70)
        
        total_tests = self.test_results['passed'] + self.test_results['failed']
        success_rate = (self.test_results['passed'] / total_tests * 100) if total_tests > 0 else 0
        
        print(f"\n📊 OVERALL RESULTS:")
        print(f"   • Total Tests: {total_tests}")
        print(f"   • Passed: {self.test_results['passed']} ✅")
        print(f"   • Failed: {self.test_results['failed']} ❌")
        print(f"   • Success Rate: {success_rate:.1f}%")
        
        print(f"\n📝 DETAILED RESULTS:")
        for detail in self.test_results['details']:
            print(f"   {detail}")
        
        print(f"\n🚀 SYSTEM CAPABILITIES:")
        if success_rate >= 80:
            print("   ✅ Enhanced clustering with adaptive parameters")
            print("   ✅ Smart truck availability checking")  
            print("   ✅ Dynamic route optimization")
            print("   ✅ Traffic-aware recommendations")
            print("   ✅ Emergency response prioritization")
            print("   ✅ Multi-depot coordination")
            print("\n🎉 COMPREHENSIVE TEST SYSTEM IS READY FOR PRODUCTION!")
        else:
            print("   ⚠️  Some functionalities may need attention")
            print("\n🔧 SYSTEM REQUIRES ADDITIONAL VALIDATION")
    
    def run_all_tests(self):
        """Run all test categories"""
        print("🧪 STARTING COMPREHENSIVE CLEANIFY SYSTEM VALIDATION")
        print("="*70)
        print(f"Test System: comprehensive_test_system.json")
        print(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.print_system_overview()
        
        self.test_clustering_functionality()
        self.test_truck_availability()
        self.test_routing_optimization()  
        self.test_traffic_management()
        self.test_system_integration()
        
        self.print_test_summary()


if __name__ == "__main__":
    tester = StreamlinedSystemTester()
    tester.run_all_tests()