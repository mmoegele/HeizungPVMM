#!/usr/bin/env python3
"""
GPIO Fix Module - Critical Monkey Patch for PiFace
==================================================

This module provides the GPIO interrupt monkey patch to prevent
PiFace initialization issues on Raspberry Pi systems.
"""

import logging

def apply_gpio_patch():
    """Apply GPIO interrupt monkey patch to fix PiFace initialization issues."""
    logger = logging.getLogger(__name__)
    
    try:
        import pifacecommon.interrupts
        
        # Replace problematic interrupt functions with safe no-ops
        def dummy_gpio_interrupts_enable():
            pass
            
        def dummy_gpio_interrupts_disable():
            pass
            
        def dummy_bring_gpio_interrupt_into_userspace():
            pass
        
        # Apply the monkey patches
        pifacecommon.interrupts.gpio_interrupts_enable = dummy_gpio_interrupts_enable
        pifacecommon.interrupts.gpio_interrupts_disable = dummy_gpio_interrupts_disable
        pifacecommon.interrupts.bring_gpio_interrupt_into_userspace = dummy_bring_gpio_interrupt_into_userspace
        
        logger.info("✅ GPIO interrupt monkey patch applied successfully")
        return True
        
    except ImportError:
        logger.debug("pifacecommon not available, GPIO patch not needed")
        return False
    except Exception as e:
        logger.warning(f"Failed to apply GPIO patch: {e}")
        return False

def test_gpio_functionality():
    """Test GPIO/PiFace functionality after applying the patch."""
    logger = logging.getLogger(__name__)
    
    try:
        if not apply_gpio_patch():
            logger.warning("GPIO patch not applied, proceeding with caution")
        
        import pifacedigitalio
        
        logger.info("Testing PiFace board initialization...")
        board = pifacedigitalio.PiFaceDigital(0)
        
        # Quick test
        board.output_pins[0].turn_on()
        board.output_pins[0].turn_off()
        
        logger.info("✅ GPIO functionality test passed")
        return True
        
    except ImportError as e:
        logger.warning(f"PiFace library not available: {e}")
        return False
    except Exception as e:
        logger.error(f"GPIO functionality test failed: {e}")
        return False

# Apply patch immediately when module is imported
_patch_applied = apply_gpio_patch()

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("🔧 GPIO Fix Module Test")
    print("=" * 30)
    
    if _patch_applied:
        print("✅ GPIO patch applied successfully")
    else:
        print("⚠️ GPIO patch not applied")
    
    if test_gpio_functionality():
        print("✅ GPIO functionality test passed")
    else:
        print("❌ GPIO functionality test failed")
