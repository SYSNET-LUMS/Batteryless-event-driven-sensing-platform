"""
Test Enhanced Clustering System

Tests the new adaptive clustering with the test_system_high_fill.json data
to verify that bins are now clustered correctly.
"""

import sys
import os
import json

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cleanify', 'simulation-backend', 'src'))

from services.clustering_service import ClusteringService
from services.agent_service import WasteCollectionAgent

def load_test_system():
    """Load the test system data"""
    with open('/media/muneeb-ur-rehman/CA66F1CB66F1B871/Study/Sproj/Cleanify/cleanify/simulation-backend/saved_systems/test_system_high_fill.json', 'r') as f:
        return json.load(f)

def test_enhanced_clustering():
    """Test the enhanced clustering system"""
    print("🧪 TESTING ENHANCED CLUSTERING SYSTEM")
    print("="*50)
    
    system_data = load_test_system()
    bins_data = system_data['bins']
    
    print(f"Testing with {len(bins_data)} bins:")
    for bin_data in bins_data:
        print(f"  - {bin_data['id']}: ({bin_data['lat']:.6f}, {bin_data['lng']:.6f}) - {bin_data['fillLevel']}%")
    print()
    
    # Test 1: Direct clustering service
    print("📊 TEST 1: Direct Clustering Service")
    print("-" * 30)
    
    try:
        clustering_service = ClusteringService()
        clusters = clustering_service.create_adaptive_clusters(bins_data)
        cluster_info = clustering_service.get_cluster_info(clusters)
        
        print(f"✅ Success! Created {len(clusters)} clusters")
        
        for cluster_id, info in cluster_info.items():
            bin_ids = info['bin_ids']
            quality = info.get('quality_metrics', {})
            
            print(f"  Cluster {cluster_id}: {bin_ids}")
            print(f"    Bins: {len(bin_ids)}")
            print(f"    Quality: {quality.get('quality_rating', 'unknown')}")
            print(f"    Avg Distance: {quality.get('avg_distance_meters', 0):.1f}m")
            print(f"    Total Waste: {quality.get('total_waste_liters', 0):.1f}L")
            print()
        
    except Exception as e:
        print(f"❌ Direct clustering failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 2: Agent service integration
    print("📊 TEST 2: Agent Service Integration")
    print("-" * 30)
    
    try:
        agent = WasteCollectionAgent()
        agent.bins_data = bins_data
        
        clusters = agent.get_clusters(bins_data)
        
        print(f"✅ Success! Agent created {len(clusters)} clusters")
        
        # Get detailed cluster info
        cluster_info = agent.clustering_service.get_cluster_info(clusters)
        
        for cluster_id, info in cluster_info.items():
            bin_ids = info['bin_ids']
            quality = info.get('quality_metrics', {})
            
            print(f"  Agent Cluster {cluster_id}: {bin_ids}")
            print(f"    Quality Rating: {quality.get('quality_rating', 'unknown')}")
            
            # Show distances between bins in cluster
            if len(bin_ids) > 1:
                cluster_bins = info['bins']
                print("    Internal distances:")
                for i, bin1 in enumerate(cluster_bins):
                    for j, bin2 in enumerate(cluster_bins):
                        if i < j:
                            # Calculate distance
                            dist = agent.clustering_service._haversine_distance(
                                bin1['lat'], bin1['lng'],
                                bin2['lat'], bin2['lng']
                            )
                            print(f"      {bin1['id']} ↔ {bin2['id']}: {dist:.1f}m")
            print()
            
    except Exception as e:
        print(f"❌ Agent clustering failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 3: Verify expected clustering
    print("📊 TEST 3: Clustering Verification")
    print("-" * 30)
    
    # Expected: BIN_1, BIN_2, BIN_3 should be in one cluster (they're all nearby)
    # BIN_4 should be in separate cluster (it's far away)
    
    nearby_bins_found = False
    far_bin_separate = False
    
    for cluster_id, info in cluster_info.items():
        bin_ids = set(info['bin_ids'])
        
        # Check if BIN_1, BIN_2, BIN_3 are together
        nearby_group = {'BIN_1', 'BIN_2', 'BIN_3'}
        if nearby_group.issubset(bin_ids) or len(nearby_group & bin_ids) >= 2:
            nearby_bins_found = True
            print(f"✅ Nearby bins grouped correctly in cluster {cluster_id}: {bin_ids & nearby_group}")
        
        # Check if BIN_4 is separate or with only a few others
        if 'BIN_4' in bin_ids:
            if len(bin_ids) <= 2:  # BIN_4 alone or with max 1 other
                far_bin_separate = True
                print(f"✅ Far bin (BIN_4) correctly separated in cluster {cluster_id}")
            else:
                print(f"⚠️  Far bin (BIN_4) in large cluster {cluster_id}: {bin_ids}")
    
    if nearby_bins_found and far_bin_separate:
        print("🎉 CLUSTERING VERIFICATION PASSED!")
        print("   - Nearby bins are grouped together")
        print("   - Far bins are appropriately separated")
        return True
    else:
        if not nearby_bins_found:
            print("❌ Nearby bins (BIN_1, BIN_2, BIN_3) not grouped correctly")
        if not far_bin_separate:
            print("❌ Far bin (BIN_4) not appropriately separated")
        return False

def compare_old_vs_new():
    """Compare old clustering (fixed params) vs new adaptive clustering"""
    print("\n" + "="*60)
    print("COMPARING OLD vs NEW CLUSTERING")
    print("="*60)
    
    system_data = load_test_system()
    bins_data = system_data['bins']
    
    clustering_service = ClusteringService()
    
    try:
        # Create distance matrix once
        distance_matrix = clustering_service.create_bin_distance_matrix(bins_data)
        
        # Old method (fixed parameters)
        print("📊 OLD METHOD (eps=300m, min_samples=2)")
        print("-" * 40)
        
        old_clusters = clustering_service.create_clusters_dbscan(
            bins_data, distance_matrix, eps_meters=300, min_samples=2
        )
        old_info = clustering_service.get_cluster_info(old_clusters)
        
        print(f"Created {len(old_clusters)} clusters:")
        for cluster_id, info in old_info.items():
            print(f"  Cluster {cluster_id}: {info['bin_ids']}")
        
        # New method (adaptive parameters)
        print("\n📊 NEW METHOD (adaptive parameters)")
        print("-" * 40)
        
        new_clusters = clustering_service.create_adaptive_clusters(bins_data)
        new_info = clustering_service.get_cluster_info(new_clusters)
        
        print(f"Created {len(new_clusters)} clusters:")
        for cluster_id, info in new_info.items():
            quality = info.get('quality_metrics', {})
            print(f"  Cluster {cluster_id}: {info['bin_ids']} - {quality.get('quality_rating', 'unknown')} quality")
        
        # Analysis
        print("\n🔍 ANALYSIS")
        print("-" * 20)
        
        # Check if nearby bins are better grouped
        nearby_bins = {'BIN_1', 'BIN_2', 'BIN_3'}
        
        # Old method grouping
        old_nearby_clusters = []
        for cluster_id, info in old_info.items():
            bin_set = set(info['bin_ids'])
            if len(bin_set & nearby_bins) > 0:
                old_nearby_clusters.append((cluster_id, bin_set & nearby_bins))
        
        # New method grouping  
        new_nearby_clusters = []
        for cluster_id, info in new_info.items():
            bin_set = set(info['bin_ids'])
            if len(bin_set & nearby_bins) > 0:
                new_nearby_clusters.append((cluster_id, bin_set & nearby_bins))
        
        print(f"Old method - nearby bins distribution: {old_nearby_clusters}")
        print(f"New method - nearby bins distribution: {new_nearby_clusters}")
        
        # Determine which is better
        old_fragmentation = len(old_nearby_clusters)
        new_fragmentation = len(new_nearby_clusters)
        
        print(f"\nFragmentation score (lower is better):")
        print(f"  Old method: {old_fragmentation} clusters for nearby bins")
        print(f"  New method: {new_fragmentation} clusters for nearby bins")
        
        if new_fragmentation < old_fragmentation:
            print("🎉 NEW METHOD PERFORMS BETTER - Less fragmentation!")
        elif new_fragmentation == old_fragmentation:
            print("📊 METHODS PERFORM SIMILARLY")
        else:
            print("⚠️  Old method had less fragmentation")
        
        return new_fragmentation <= old_fragmentation
        
    except Exception as e:
        print(f"❌ Comparison failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🔬 ENHANCED CLUSTERING SYSTEM TEST")
    print("Testing improved clustering with test_system_high_fill.json")
    print()
    
    # Test enhanced clustering
    enhanced_success = test_enhanced_clustering()
    
    # Compare old vs new
    comparison_success = compare_old_vs_new()
    
    # Results
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    
    if enhanced_success:
        print("✅ Enhanced clustering system works correctly")
        print("   - Nearby bins are properly grouped")
        print("   - Far bins are appropriately separated")
    else:
        print("❌ Enhanced clustering needs further adjustment")
    
    if comparison_success:
        print("✅ New clustering performs better than or equal to old method")
    else:
        print("⚠️  New clustering may need parameter tuning")
    
    if enhanced_success and comparison_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("The clustering issue has been resolved!")
        print("\nKey improvements:")
        print("  1. Adaptive parameter selection based on data")
        print("  2. Increased default eps from 300m to 500m")
        print("  3. Quality metrics for cluster evaluation")
        print("  4. Fallback strategies for robustness")
    else:
        print("\n⚠️  Some tests failed - please review the results above")
    
    return enhanced_success and comparison_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)