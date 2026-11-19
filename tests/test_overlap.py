import unittest

from overlap_cases import OverlapExamples, check_v1


class V1ProjectionTests(unittest.TestCase):
    def test_normalized_v1_projection(self):
        check_v1()


__all__ = ['OverlapExamples', 'V1ProjectionTests']


if __name__ == '__main__':
    unittest.main()
